import time

import sounddevice as sd
from faster_whisper import WhisperModel


# 输入设备索引：设为 None 时使用系统默认输入设备
DEVICE_INDEX = 7

# 录音参数
SAMPLE_RATE = 16000
CHANNELS = 1
DURATION_SECONDS = 5

# Whisper 模型大小
MODEL_SIZE = "tiny"
COMPUTE_TYPE = "int8"


def list_input_devices() -> list[int]:
    """列出所有可用的音频输入设备，返回可用输入设备索引列表。"""
    devices = sd.query_devices()
    input_indices: list[int] = []

    print("可用音频输入设备：")
    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) > 0:
            input_indices.append(index)
            print(f"  [{index}] {device.get('name', 'Unknown Device')}")

    if not input_indices:
        print("未检测到可用的音频输入设备。")
    return input_indices


def get_selected_device() -> int | None:
    """根据 DEVICE_INDEX 选择设备，None 表示使用系统默认输入设备。"""
    if DEVICE_INDEX is None:
        default_device = sd.default.device
        # sd.default.device 通常为 (input_index, output_index)
        if isinstance(default_device, (tuple, list)) and len(default_device) >= 1:
            print(f"当前使用系统默认输入设备：{default_device[0]}")
        else:
            print("当前使用系统默认输入设备。")
        return None

    print(f"当前使用指定输入设备：{DEVICE_INDEX}")
    return DEVICE_INDEX


def resolve_input_device_index(device_index: int | None) -> int | None:
    """解析实际使用的输入设备 index，用于打印确认输入来源。"""
    if device_index is not None:
        return device_index
    default_device = sd.default.device
    if isinstance(default_device, (tuple, list)) and len(default_device) >= 1:
        return default_device[0]
    return None


def record_audio(device_index: int | None):
    """录制指定时长音频并返回一维 float32 numpy 数组。"""
    frames = int(SAMPLE_RATE * DURATION_SECONDS)
    actual_index = resolve_input_device_index(device_index)
    print(f"录音输入设备 index: {actual_index}")
    print(f"\n开始录音（{DURATION_SECONDS} 秒）...")
    recording = sd.rec(
        frames,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        device=device_index,
    )
    sd.wait()
    print("录音完成。")

    # 单声道数据 shape 为 (N, 1)，转成一维以便传给 Whisper
    return recording[:, 0]


def transcribe_audio(audio_data):
    """使用 faster-whisper 模型进行转写，返回文本与耗时。"""
    start = time.perf_counter()

    # CPU 场景下 int8 更轻量；若有 GPU 可自行改为 device="cuda"
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE)
    segments, _ = model.transcribe(audio_data, language="en", beam_size=1)
    text = "".join(segment.text for segment in segments).strip()

    elapsed = time.perf_counter() - start
    return text, elapsed


def main() -> None:
    total_start = time.perf_counter()

    available_inputs = list_input_devices()
    if not available_inputs:
        return

    selected_device = get_selected_device()
    audio_data = record_audio(selected_device)

    print("\n开始转写...")
    text, transcribe_elapsed = transcribe_audio(audio_data)
    total_elapsed = time.perf_counter() - total_start

    print("\n=== 转写结果 ===")
    print(text if text else "(未识别到有效语音)")
    print(f"\n转写耗时: {transcribe_elapsed:.2f} 秒")
    print(f"总耗时(含录音): {total_elapsed:.2f} 秒")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n运行失败：{exc}")
        print("请确认已安装依赖：pip install sounddevice faster-whisper")
