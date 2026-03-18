import queue
import threading
import time
from typing import Any

import sounddevice as sd
from faster_whisper import WhisperModel

import config

SAMPLE_RATE = 16000
CHANNELS = 1

_stop_event = threading.Event()
_listener_thread: threading.Thread | None = None
_transcript_queue: queue.Queue[str] | None = None


def list_input_devices() -> list[tuple[int, str]]:
    """列出可用音频输入设备。"""
    result: list[tuple[int, str]] = []
    try:
        devices = sd.query_devices()
        for index, device in enumerate(devices):
            if device.get("max_input_channels", 0) > 0:
                name = str(device.get("name", "Unknown Device"))
                result.append((index, name))
        return result
    except Exception as exc:
        print(f"[audio] 列出输入设备失败: {exc}")
        return result


def create_whisper_model() -> WhisperModel:
    """按配置创建 Whisper 模型实例。"""
    return WhisperModel(
        config.WHISPER_MODEL,
        device="cpu",
        compute_type=config.WHISPER_COMPUTE_TYPE,
    )


def record_chunk(seconds: int = config.CHUNK_SECONDS) -> Any:
    """录制一段音频数据，返回一维 float32 数组。"""
    frames = int(SAMPLE_RATE * seconds)
    recording = sd.rec(
        frames,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        device=config.AUDIO_DEVICE_INDEX,
    )
    sd.wait()
    return recording[:, 0]


def transcribe_chunk(model: WhisperModel, audio_data: Any) -> str:
    """转写音频片段并返回文本。"""
    hotwords = ", ".join(config.WHISPER_HOTWORDS)
    start = time.perf_counter()
    segments, _ = model.transcribe(
        audio_data,
        language=config.WHISPER_LANGUAGE,
        beam_size=config.WHISPER_BEAM_SIZE,
        hotwords=hotwords,
    )
    text = "".join(segment.text for segment in segments).strip()
    elapsed = time.perf_counter() - start
    print(f"转写耗时: {elapsed:.2f} 秒 | 内容: [{text}]")
    return text


def _is_valid_transcript(text: str) -> bool:
    """过滤空字符串和少于 3 个词的文本，减少噪音幻觉。"""
    if not text:
        return False
    return len(text.split()) >= 3


def _listening_loop() -> None:
    """后台监听线程：持续录音并转写，把文本写入队列。"""
    model: WhisperModel | None = None
    while not _stop_event.is_set():
        try:
            if _transcript_queue is None:
                print("[audio] 转写队列未初始化，等待重试...")
                time.sleep(0.2)
                continue

            if model is None:
                print(
                    f"[audio] 初始化 Whisper: model={config.WHISPER_MODEL}, "
                    f"compute_type={config.WHISPER_COMPUTE_TYPE}"
                )
                model = create_whisper_model()
                print(
                    f"[audio] 开始监听: device={config.AUDIO_DEVICE_INDEX}, "
                    f"sample_rate={SAMPLE_RATE}, channels={CHANNELS}, "
                    f"chunk={config.CHUNK_SECONDS}s"
                )

            audio_data = record_chunk(config.CHUNK_SECONDS)
            text = transcribe_chunk(model, audio_data)

            if _is_valid_transcript(text):
                _transcript_queue.put(text)
            else:
                print(f"[audio] 忽略短文本/空文本: {text!r}")
        except Exception as exc:
            # 所有异常都吞掉并继续循环，避免后台线程崩溃
            print(f"[audio] 监听线程异常: {exc}")
            time.sleep(0.5)


def start_listening(transcript_queue: queue.Queue[str]) -> None:
    """启动后台线程开始捕获并转写音频。"""
    global _listener_thread, _transcript_queue

    try:
        if _listener_thread is not None and _listener_thread.is_alive():
            print("[audio] 监听线程已在运行，跳过重复启动。")
            return

        _transcript_queue = transcript_queue
        _stop_event.clear()
        _listener_thread = threading.Thread(
            target=_listening_loop,
            name="audio-listener",
            daemon=True,
        )
        _listener_thread.start()
    except Exception as exc:
        print(f"[audio] 启动监听失败: {exc}")


def stop_listening() -> None:
    """停止后台监听线程。"""
    global _listener_thread

    try:
        _stop_event.set()
        if _listener_thread is not None and _listener_thread.is_alive():
            _listener_thread.join(timeout=3.0)
        _listener_thread = None
        print("[audio] 监听已停止。")
    except Exception as exc:
        print(f"[audio] 停止监听失败: {exc}")


if __name__ == "__main__":
    q: queue.Queue[str] = queue.Queue()
    start_listening(q)
    print("音频监听测试已启动，按 Ctrl+C 退出。")

    try:
        while True:
            try:
                transcript = q.get(timeout=1.0)
                print(f"[transcript] {transcript}")
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        print("\n收到退出信号，正在停止...")
    finally:
        stop_listening()
