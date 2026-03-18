from __future__ import annotations

import queue
import threading
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

    def setup(self) -> None:
        """初始化 UI、回调与后台线程。"""
        self.ui_state = ui.create_ui()
        ui.set_photo_callback(self.ui_state, self.on_photo_clicked)
        ui.set_pause_callback(self.ui_state, self.on_pause_toggled)
        self.ui_state.root.bind("<Destroy>", self._on_root_destroy, add="+")

        audio.start_listening(self.transcript_queue)
        ui.set_status(self.ui_state, True)

        self.consumer_thread = threading.Thread(
            target=self._consume_transcripts_loop,
            name="transcript-consumer",
            daemon=True,
        )
        self.consumer_thread.start()
        print("[main] 应用初始化完成。")

    def run(self) -> None:
        """运行 UI 主循环。"""
        if self.ui_state is None:
            self.setup()
        try:
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
            try:
                transcript = self.transcript_queue.get(timeout=0.3)
            except queue.Empty:
                continue
            except Exception as exc:
                print(f"[main] 读取 transcript 队列失败: {exc}")
                continue

            if not transcript:
                continue

            self._ui_call(ui.append_transcript, transcript + "\n")

            def on_token(token: str) -> None:
                self._ui_call(ui.append_answer, token)

            try:
                answer = llm.analyze_text(transcript, on_token=on_token)
                if answer:
                    self._ui_call(ui.append_answer, "\n\n")
            except Exception as exc:
                print(f"[main] 文本分析失败: {exc}")

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
