from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import audio
import llm
import ui
import vision


class AppController:
    """主程序控制器：串联音频、视觉、LLM 与 UI。"""

    def __init__(self) -> None:
        self.transcript_queue: queue.Queue[str] = queue.Queue()
        self.stop_event = threading.Event()
        self.consumer_thread: threading.Thread | None = None
        self.ui_state: Any = None
        self.auto_mode_enabled = False
        self.pending_transcript_parts: list[str] = []
        self.last_transcript_ts: float | None = None
        self.silence_threshold_sec = 2.0
        self.llm_in_flight = False
        self.state_lock = threading.Lock()
        self.audio_boot_thread: threading.Thread | None = None
        self.transcript_log_path = Path(__file__).with_name("transcripts.txt")

    def setup(self) -> None:
        """初始化 UI、回调与后台线程。"""
        # 1) 先初始化 UI（主线程）
        self.ui_state = ui.create_ui()
        ui.set_photo_callback(self.ui_state, self.on_photo_clicked)
        ui.set_pause_callback(self.ui_state, self.on_pause_toggled)
        ui.set_mode_toggle_callback(self.ui_state, self.on_mode_toggled)
        ui.set_manual_trigger_callback(self.ui_state, self.on_manual_trigger)
        self.ui_state.root.bind("<Destroy>", self._on_root_destroy, add="+")

        # 2) 音频监听放到后台线程启动，避免阻塞 UI 初始化
        self.audio_boot_thread = threading.Thread(
            target=audio.start_listening,
            args=(self.transcript_queue,),
            name="audio-bootstrap",
            daemon=True,
        )
        self.audio_boot_thread.start()
        ui.set_status(self.ui_state, True)

        self.consumer_thread = threading.Thread(
            target=self._consume_transcripts_loop,
            name="transcript-consumer",
            daemon=True,
        )
        self.consumer_thread.start()
        print("[main] 应用初始化完成。")

    def run(self) -> None:
        """运行 UI 主循环（必须在主线程）。"""
        if self.ui_state is None:
            self.setup()
        try:
            # 3) 最后进入 Tk 主循环
            ui.run_ui(self.ui_state)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """停止后台任务并清理资源。"""
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        audio.stop_listening()
        if self.consumer_thread and self.consumer_thread.is_alive():
            self.consumer_thread.join(timeout=2.0)
        print("[main] 应用已退出。")

    # ---- UI 回调 ----
    def on_pause_toggled(self, listening: bool) -> None:
        """暂停/继续按钮回调：控制音频监听线程。"""
        if listening:
            audio.start_listening(self.transcript_queue)
            print("[main] 监听已继续。")
        else:
            audio.stop_listening()
            print("[main] 监听已暂停。")

    def on_mode_toggled(self, enabled: bool) -> None:
        """模式切换回调：True=Auto（静音触发），False=Manual（按钮触发）。"""
        with self.state_lock:
            self.auto_mode_enabled = enabled
            self.pending_transcript_parts.clear()
            self.last_transcript_ts = None

        self._drain_transcript_queue()
        mode_name = "AUTO" if enabled else "MANUAL"
        print(f"[main] Mode changed -> {mode_name}")

    def on_manual_trigger(self) -> None:
        """手动触发 LLM（仅 Manual 模式生效）。"""
        with self.state_lock:
            if self.auto_mode_enabled:
                print("[main] Manual trigger ignored (auto mode enabled).")
                return
            if self.llm_in_flight:
                print("[main] Manual trigger skipped (LLM call already running).")
                return

            text = self.ui_state._stt_buffer.strip()
            if not text:
                print("[main] Manual trigger skipped (no transcript buffer).")
                return
            print("Trigger text:", text)

            # 先落盘，再清空内存与 UI（会话化输入）
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with self.transcript_log_path.open("a", encoding="utf-8") as f:
                    f.write(f"\n---\n[{timestamp}]\n{text}\n")
            except Exception as exc:
                print(f"[main] transcript save failed: {exc}")

            self.llm_in_flight = True
            self.pending_transcript_parts.clear()
            self.last_transcript_ts = None

        self._ui_call(ui.clear_transcript)
        print("[main] transcript saved and cleared")
        print("[main] Trigger fired: manual")
        audio.stop_listening()
        threading.Thread(
            target=self._run_text_llm_flow,
            args=(text, "manual"),
            name="manual-llm",
            daemon=True,
        ).start()

    def on_photo_clicked(self) -> None:
        """拍照按钮回调：后台拍照并进行视觉分析。"""
        thread = threading.Thread(
            target=self._photo_flow,
            name="photo-flow",
            daemon=True,
        )
        thread.start()

    # ---- 后台流程 ----
    def _consume_transcripts_loop(self) -> None:
        """消费音频转写队列，并驱动 UI + LLM 分析。"""
        while not self.stop_event.is_set():
            transcript = ""
            try:
                transcript = self.transcript_queue.get(timeout=0.3)
            except queue.Empty:
                pass
            except Exception as exc:
                print(f"[main] 读取 transcript 队列失败: {exc}")
                continue

            if transcript:
                self._ui_call(ui.append_transcript, transcript + "\n")
                with self.state_lock:
                    self.pending_transcript_parts.append(transcript)
                    self.last_transcript_ts = time.monotonic()

            self._maybe_trigger_auto_llm()

    def _photo_flow(self) -> None:
        """执行拍照与图片分析流程。"""
        try:
            self._ui_call(ui.append_answer, "\n[Photo] Opening camera...\n")
            image_path = vision.capture_photo()
            if not image_path:
                self._ui_call(ui.append_answer, "[Photo] Cancelled or failed.\n")
                return

            self._ui_call(ui.append_answer, f"[Photo] Captured: {image_path}\n")

            def on_token(token: str) -> None:
                self._ui_call(ui.append_answer, token)

            result = vision.analyze_image(image_path, on_token=on_token)
            if result:
                self._ui_call(ui.append_answer, "\n\n")
            else:
                self._ui_call(ui.append_answer, "[Photo] No analysis result.\n")
        except Exception as exc:
            print(f"[main] 拍照流程失败: {exc}")

    def _maybe_trigger_auto_llm(self) -> None:
        """Auto 模式下：静音达到阈值时自动触发一次 LLM。"""
        with self.state_lock:
            if not self.auto_mode_enabled:
                return
            if self.llm_in_flight:
                return
            if not self.pending_transcript_parts:
                return
            if self.last_transcript_ts is None:
                return
            if (time.monotonic() - self.last_transcript_ts) < self.silence_threshold_sec:
                return

            text = " ".join(self.pending_transcript_parts).strip()
            if not text:
                self.pending_transcript_parts.clear()
                self.last_transcript_ts = None
                return

            self.llm_in_flight = True
            self.pending_transcript_parts.clear()
            self.last_transcript_ts = None

        print("[main] Trigger fired: auto (silence detected)")
        threading.Thread(
            target=self._run_text_llm_flow,
            args=(text, "auto"),
            name="auto-llm",
            daemon=True,
        ).start()

    def _run_text_llm_flow(self, text: str, trigger_source: str) -> None:
        """统一文本分析流程，支持 streaming token 到 UI。"""
        try:
            self._ui_call(ui.append_answer, f"\n[{trigger_source}] ")

            def on_token(token: str) -> None:
                self._ui_call(ui.append_answer, token)

            answer = llm.analyze_text(text, on_token=on_token)
            if answer:
                self._ui_call(ui.append_answer, "\n\n")
        except Exception as exc:
            print(f"[main] 文本分析失败 ({trigger_source}): {exc}")
        finally:
            with self.state_lock:
                self.llm_in_flight = False
            if trigger_source == "manual":
                audio.start_listening(self.transcript_queue)

    def _drain_transcript_queue(self) -> None:
        """模式切换时清空队列，避免旧片段触发新模式逻辑。"""
        drained = 0
        while True:
            try:
                self.transcript_queue.get_nowait()
                drained += 1
            except queue.Empty:
                break
            except Exception as exc:
                print(f"[main] 清空 transcript 队列失败: {exc}")
                break
        if drained:
            print(f"[main] Cleared pending transcripts: {drained}")

    # ---- 线程安全 UI 调度 ----
    def _ui_call(self, fn, *args) -> None:
        """把 UI 更新调度到 tkinter 主线程。"""
        if self.ui_state is None:
            return
        try:
            self.ui_state.root.after(0, lambda: fn(self.ui_state, *args))
        except Exception as exc:
            print(f"[main] UI 调度失败: {exc}")

    def _on_root_destroy(self, _event) -> None:
        """窗口销毁时兜底清理。"""
        self.shutdown()


def setup() -> AppController:
    """初始化应用并返回控制器。"""
    app = AppController()
    app.setup()
    return app


def run() -> None:
    """启动主流程。"""
    app = AppController()
    app.run()


def main() -> None:
    """程序入口。"""
    run()


if __name__ == "__main__":
    main()
