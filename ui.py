from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Any, Callable

import config

BG_MAIN = "#1a1a1a"
BG_DARK = "#111111"
FG_MAIN = "#d4d4d4"
FG_MUTED = "#666666"
FG_STT = "#aaaaaa"
SEP = "#333333"


class CopilotUI:
    """面试辅助悬浮窗 UI。"""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", config.UI_OPACITY)
        self.root.configure(bg=BG_MAIN)
        self.root.geometry(self._calc_start_geometry())

        self._photo_callback: Callable[[], None] | None = None
        self._pause_callback: Callable[[bool], None] | None = None
        self._mode_toggle_callback: Callable[[bool], None] | None = None
        self._manual_trigger_callback: Callable[[], None] | None = None
        self._is_listening = True
        self._auto_mode_enabled = False

        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._resize_start_y = 0
        self._resize_start_height = 0
        self._min_window_height = 250
        self._max_window_height = 1000
        self._stt_buffer = ""

        self._build_layout()
        self._bind_mousewheel()
        self.set_status(True)

    def _calc_start_geometry(self) -> str:
        """计算窗口右下角初始位置，距屏幕边缘 20px。"""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, screen_w - config.UI_WIDTH - 20)
        y = max(0, screen_h - config.UI_HEIGHT - 20)
        return f"{config.UI_WIDTH}x{config.UI_HEIGHT}+{x}+{y}"

    def _build_layout(self) -> None:
        # 顶部标题栏
        self.header = tk.Frame(self.root, bg=BG_DARK, height=28)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        self.status_dot = tk.Canvas(
            self.header, width=10, height=10, bg=BG_DARK, highlightthickness=0
        )
        self.status_dot.pack(side="left", padx=(8, 4))
        self._dot_id = self.status_dot.create_oval(1, 1, 9, 9, fill="#22c55e", outline="")

        self.status_label = tk.Label(
            self.header,
            text="Listening",
            bg=BG_DARK,
            fg=FG_MAIN,
            font=("Segoe UI", 10),
        )
        self.status_label.pack(side="left")

        self.clear_btn = tk.Button(
            self.header,
            text="✕",
            bg=BG_DARK,
            fg="#999999",
            bd=0,
            relief="flat",
            activebackground=BG_DARK,
            activeforeground="#dddddd",
            command=self.clear_all,
            cursor="hand2",
        )
        self.clear_btn.pack(side="right", padx=8)

        # 绑定拖动
        self.header.bind("<ButtonPress-1>", self._on_drag_start)
        self.header.bind("<B1-Motion>", self._on_drag_move)
        self.status_label.bind("<ButtonPress-1>", self._on_drag_start)
        self.status_label.bind("<B1-Motion>", self._on_drag_move)

        # 底部自定义 resize handle（overrideredirect 场景）
        self.resize_bar = tk.Frame(
            self.root,
            bg=SEP,
            height=4,
            cursor="sb_v_double_arrow",
        )
        self.resize_bar.pack(fill="x", side="bottom")
        self.resize_bar.pack_propagate(False)
        self.resize_bar.bind("<ButtonPress-1>", self._on_resize_start)
        self.resize_bar.bind("<B1-Motion>", self._on_resizing)

        # 底部模式+工具栏容器（确保按钮始终可见）
        mode_bar = tk.Frame(self.root, bg=BG_DARK, height=64)
        mode_bar.pack(fill="x", side="bottom")
        mode_bar.pack_propagate(False)

        # 中间内容区：上方 AI Answer、下方 STT，可拖拽分隔
        content_pane = tk.PanedWindow(
            self.root,
            orient="vertical",
            bg=BG_MAIN,
            sashwidth=6,
            sashrelief="flat",
            showhandle=False,
        )
        content_pane.pack(fill="both", expand=True)

        # AI Answer 区域（顶部）
        answer_wrap = tk.Frame(content_pane, bg=BG_MAIN)
        answer_text_wrap = tk.Frame(answer_wrap, bg=BG_MAIN)
        answer_text_wrap.pack(fill="both", expand=True, padx=8, pady=6)

        self.answer_text = tk.Text(
            answer_text_wrap,
            bg=BG_MAIN,
            fg=FG_MAIN,
            insertbackground=FG_MAIN,
            relief="flat",
            bd=0,
            font=tkfont.Font(family="Consolas", size=10),
            wrap="word",
            spacing1=2,
            spacing2=6,
            spacing3=2,
            padx=6,
            pady=4,
            state="disabled",
        )
        self.answer_text.pack(side="left", fill="both", expand=True)

        # 右侧 2px 滚动位置线（隐藏原生 scrollbar）
        self.answer_scrollbar = tk.Canvas(
            answer_text_wrap, width=2, bg=BG_MAIN, highlightthickness=0
        )
        self.answer_scrollbar.pack(side="right", fill="y")
        self._scroll_thumb = self.answer_scrollbar.create_rectangle(
            0, 0, 2, 24, fill=SEP, outline=SEP
        )

        # STT 区域（底部，紧凑单行感）
        stt_wrap = tk.Frame(content_pane, bg=BG_MAIN)
        stt_text_wrap = tk.Frame(stt_wrap, bg=BG_DARK)
        stt_text_wrap.pack(fill="both", expand=True, padx=8, pady=4)

        self.stt_text = tk.Text(
            stt_text_wrap,
            bg=BG_DARK,
            fg=FG_STT,
            insertbackground="#22c55e",
            relief="flat",
            bd=0,
            font=tkfont.Font(family="Consolas", size=10),
            wrap="word",
            padx=6,
            pady=4,
            state="disabled",
        )
        self.stt_text.pack(fill="both", expand=True)

        content_pane.add(answer_wrap, minsize=180)
        content_pane.add(stt_wrap, minsize=90)

        self.auto_mode_var = tk.BooleanVar(value=False)
        self.auto_mode_toggle = tk.Checkbutton(
            mode_bar,
            text="Auto Mode (Silence Detection)",
            variable=self.auto_mode_var,
            bg=BG_DARK,
            fg=FG_MAIN,
            activebackground=BG_DARK,
            activeforeground=FG_MAIN,
            selectcolor=BG_DARK,
            font=("Segoe UI", 9),
            command=self._on_mode_toggle,
            cursor="hand2",
            bd=0,
            highlightthickness=0,
        )
        self.auto_mode_toggle.pack(side="top", anchor="w", padx=8, pady=(2, 0))

        # 底部工具栏（嵌套在 mode_bar 内）
        toolbar = tk.Frame(mode_bar, bg="#222222", height=36)
        toolbar.pack(fill="x", side="bottom", pady=(0, 2))
        toolbar.pack_propagate(False)

        self.photo_btn = tk.Button(
            toolbar,
            text="📷 拍照",
            bg="#1e3a5f",
            fg="#93c5fd",
            activebackground="#1f4170",
            activeforeground="#bfdbfe",
            highlightbackground="#2563eb",
            highlightthickness=1,
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self._on_photo_click,
        )
        self.photo_btn.pack(side="left", padx=8, pady=6)

        self.manual_trigger_btn = tk.Button(
            toolbar,
            text="🧠 Trigger",
            bg="#1f1f1f",
            fg=FG_MAIN,
            activebackground="#2a2a2a",
            activeforeground="#ffffff",
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self._on_manual_trigger_click,
        )
        self.manual_trigger_btn.pack(side="left", padx=4, pady=6)

        self.pause_btn = tk.Button(
            toolbar,
            text="⏸ 暂停",
            bg=BG_DARK,
            fg=FG_MAIN,
            activebackground="#1b1b1b",
            activeforeground="#f5f5f5",
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self._on_pause_click,
        )
        self.pause_btn.pack(side="right", padx=8, pady=6)

        self.answer_text.bind("<Configure>", lambda _: self._update_answer_scroll_indicator())
        self.answer_text.bind("<Key>", lambda _: "break")
        self.stt_text.bind("<Key>", lambda _: "break")

    def _bind_mousewheel(self) -> None:
        self.stt_text.bind("<MouseWheel>", self._on_stt_wheel)
        self.answer_text.bind("<MouseWheel>", self._on_answer_wheel)
        # 兼容部分 Linux 触控板/鼠标事件
        self.stt_text.bind("<Button-4>", lambda _: self._scroll_stt(-1))
        self.stt_text.bind("<Button-5>", lambda _: self._scroll_stt(1))
        self.answer_text.bind("<Button-4>", lambda _: self._scroll_answer(-1))
        self.answer_text.bind("<Button-5>", lambda _: self._scroll_answer(1))

    def _on_stt_wheel(self, event: tk.Event) -> str:
        step = -1 if event.delta > 0 else 1
        self._scroll_stt(step)
        return "break"

    def _on_answer_wheel(self, event: tk.Event) -> str:
        step = -1 if event.delta > 0 else 1
        self._scroll_answer(step)
        return "break"

    def _scroll_stt(self, step: int) -> None:
        self.stt_text.yview_scroll(step, "units")

    def _scroll_answer(self, step: int) -> None:
        self.answer_text.yview_scroll(step, "units")
        self._update_answer_scroll_indicator()

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_offset_x = event.x
        self._drag_offset_y = event.y

    def _on_drag_move(self, event: tk.Event) -> None:
        x = self.root.winfo_pointerx() - self._drag_offset_x
        y = self.root.winfo_pointery() - self._drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    def _on_resize_start(self, event: tk.Event) -> None:
        self._resize_start_y = event.y_root
        self._resize_start_height = self.root.winfo_height()

    def _on_resizing(self, event: tk.Event) -> None:
        delta_y = event.y_root - self._resize_start_y
        new_height = self._resize_start_height + delta_y
        new_height = max(self._min_window_height, new_height)
        new_height = min(self._max_window_height, new_height)

        width = self.root.winfo_width()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{width}x{int(new_height)}+{x}+{y}")

    def _is_at_bottom(self, widget: tk.Text) -> bool:
        first, last = widget.yview()
        return last >= 0.999

    def _set_text_content(self, widget: tk.Text, content: str) -> None:
        is_at_bottom = self._is_at_bottom(widget)
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", content)
        widget.config(state="disabled")
        if is_at_bottom:
            widget.see("end")

    def _append_text(self, widget: tk.Text, text: str) -> None:
        is_at_bottom = self._is_at_bottom(widget)
        widget.config(state="normal")
        widget.insert("end", text)
        widget.config(state="disabled")
        if is_at_bottom:
            widget.see("end")

    def _update_answer_scroll_indicator(self) -> None:
        self.answer_scrollbar.update_idletasks()
        h = max(1, self.answer_scrollbar.winfo_height())
        first, last = self.answer_text.yview()
        y1 = int(first * h)
        y2 = int(last * h)
        y2 = max(y1 + 10, y2)
        y2 = min(h, y2)
        self.answer_scrollbar.coords(self._scroll_thumb, 0, y1, 2, y2)

    def _on_photo_click(self) -> None:
        if self._photo_callback:
            try:
                self._photo_callback()
            except Exception as exc:
                print(f"[ui] photo callback 失败: {exc}")

    def _on_pause_click(self) -> None:
        self._is_listening = not self._is_listening
        self.set_status(self._is_listening)
        self.pause_btn.config(text="⏸ 暂停" if self._is_listening else "▶ 继续")
        if self._pause_callback:
            try:
                self._pause_callback(self._is_listening)
            except TypeError:
                # 兼容无参回调
                self._pause_callback()
            except Exception as exc:
                print(f"[ui] pause callback 失败: {exc}")

    def _on_mode_toggle(self) -> None:
        self._auto_mode_enabled = bool(self.auto_mode_var.get())
        # 自动模式下禁用手动触发按钮，确保只保留单一触发入口
        self.manual_trigger_btn.config(
            state=("disabled" if self._auto_mode_enabled else "normal")
        )
        if self._mode_toggle_callback:
            try:
                self._mode_toggle_callback(self._auto_mode_enabled)
            except Exception as exc:
                print(f"[ui] mode toggle callback 失败: {exc}")

    def _on_manual_trigger_click(self) -> None:
        if self._auto_mode_enabled:
            return
        if self._manual_trigger_callback:
            try:
                self._manual_trigger_callback()
            except Exception as exc:
                print(f"[ui] manual trigger callback 失败: {exc}")

    # ---- 对外公开方法 ----
    def append_transcript(self, text: str) -> None:
        if not text:
            return
        self._stt_buffer += text
        self._append_text(self.stt_text, text)

    def append_answer(self, text: str) -> None:
        if not text:
            return
        self._append_text(self.answer_text, text)
        self._update_answer_scroll_indicator()

    def clear_all(self) -> None:
        self._stt_buffer = ""
        self._set_text_content(self.stt_text, "")
        self._set_text_content(self.answer_text, "")
        self._update_answer_scroll_indicator()

    def clear_transcript(self) -> None:
        self._stt_buffer = ""
        self._set_text_content(self.stt_text, "")

    def set_status(self, listening: bool) -> None:
        self._is_listening = listening
        color = "#22c55e" if listening else "#ef4444"
        text = "Listening" if listening else "Paused"
        self.status_dot.itemconfig(self._dot_id, fill=color)
        self.status_label.config(text=text)
        self.pause_btn.config(text="⏸ 暂停" if listening else "▶ 继续")

    def set_photo_callback(self, callback: Callable[[], None]) -> None:
        self._photo_callback = callback

    def set_pause_callback(self, callback: Callable[[bool], None]) -> None:
        self._pause_callback = callback

    def set_mode_toggle_callback(self, callback: Callable[[bool], None]) -> None:
        self._mode_toggle_callback = callback

    def set_manual_trigger_callback(self, callback: Callable[[], None]) -> None:
        self._manual_trigger_callback = callback

    def run(self) -> None:
        self.root.mainloop()


def create_ui() -> Any:
    """创建主界面。"""
    return CopilotUI()


def append_transcript(ui_state: Any, text: str) -> None:
    """追加文字到 STT Console。"""
    ui_state.append_transcript(text)


def append_answer(ui_state: Any, text: str) -> None:
    """追加文字到 AI Answer。"""
    ui_state.append_answer(text)


def clear_all(ui_state: Any) -> None:
    """清空两个区域。"""
    ui_state.clear_all()


def clear_transcript(ui_state: Any) -> None:
    """仅清空 STT 区域。"""
    ui_state._stt_buffer = ""
    widget = ui_state.stt_text
    widget.config(state="normal")
    widget.delete("1.0", "end")
    widget.config(state="disabled")
    print("[ui] STT cleared")


def set_status(ui_state: Any, listening: bool) -> None:
    """切换顶部状态圆点颜色与文字。"""
    ui_state.set_status(listening)


def set_photo_callback(ui_state: Any, callback: Callable[[], None]) -> None:
    """设置拍照按钮回调。"""
    ui_state.set_photo_callback(callback)


def set_pause_callback(ui_state: Any, callback: Callable[[bool], None]) -> None:
    """设置暂停按钮回调。"""
    ui_state.set_pause_callback(callback)


def set_mode_toggle_callback(ui_state: Any, callback: Callable[[bool], None]) -> None:
    """设置模式切换回调（True=Auto, False=Manual）。"""
    ui_state.set_mode_toggle_callback(callback)


def set_manual_trigger_callback(ui_state: Any, callback: Callable[[], None]) -> None:
    """设置手动触发按钮回调。"""
    ui_state.set_manual_trigger_callback(callback)


def update_transcript(ui_state: Any, text: str) -> None:
    """兼容旧接口：更新转写文本区域。"""
    append_transcript(ui_state, text)


def update_answer(ui_state: Any, text: str) -> None:
    """兼容旧接口：更新回答文本区域。"""
    append_answer(ui_state, text)


def run_ui(ui_state: Any) -> None:
    """启动 UI 主循环。"""
    ui_state.run()


if __name__ == "__main__":
    ui = create_ui()

    set_photo_callback(ui, lambda: print("[ui test] 点击了拍照按钮"))
    set_pause_callback(ui, lambda listening: print(f"[ui test] listening={listening}"))

    stt_samples = [
        "What is JIT compiler? ",
        "How does a hash map handle collisions? ",
        "Describe a time you fixed a production incident. ",
    ]
    answer_samples = [
        "- JIT compiles bytecode to native code at runtime.\n",
        "- Benefits: faster hot-path execution, adaptive optimization.\n",
        "- Tradeoff: warm-up cost and extra runtime complexity.\n\n",
    ]
    state = {"stt_idx": 0, "ans_idx": 0}

    def feed_stt() -> None:
        idx = state["stt_idx"]
        append_transcript(ui, stt_samples[idx % len(stt_samples)])
        state["stt_idx"] = idx + 1
        ui.root.after(1000, feed_stt)

    def feed_answer_stream() -> None:
        idx = state["ans_idx"]
        block = answer_samples[idx % len(answer_samples)]
        state["ans_idx"] = idx + 1

        def stream_chars(i: int = 0) -> None:
            if i >= len(block):
                return
            append_answer(ui, block[i])
            ui.root.after(35, lambda: stream_chars(i + 1))

        stream_chars()
        ui.root.after(3000, feed_answer_stream)

    ui.root.after(500, feed_stt)
    ui.root.after(1000, feed_answer_stream)
    run_ui(ui)
