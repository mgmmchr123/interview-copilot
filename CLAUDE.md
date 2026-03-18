# Interview Copilot 项目说明

## 项目目标

构建一个本地运行的面试辅助工具，整合音频转写、相机画面上下文、LLM 回答生成与轻量 UI 展示。

## 当前模块架构

- `config.py`：统一管理配置参数与环境变量读取。
- `main.py`：应用入口与流程调度骨架。
- `audio.py`：音频输入、Whisper 模型创建、分段录音与转写骨架。
- `vision.py`：相机目录监控与图像分析骨架。
- `llm.py`：Anthropic 客户端与提示词/回答生成骨架。
- `ui.py`：界面创建与文本更新骨架。
- `test_audio.py`：独立的录音+转写验证脚本（已验证通过）。

## 已确认配置参数

- `AUDIO_DEVICE_INDEX = 7`
- `WHISPER_MODEL = "tiny"`
- `WHISPER_LANGUAGE = "en"`
- `WHISPER_COMPUTE_TYPE = "int8"`
- `WHISPER_BEAM_SIZE = 1`
- `CHUNK_SECONDS = 4`
- `ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")`
- `CAMERA_WATCH_FOLDER = os.path.expanduser("~/Pictures/Camera Roll")`
- `UI_WIDTH = 320`
- `UI_HEIGHT = 580`
- `UI_OPACITY = 0.92`

## 说明

当前阶段仅完成基础框架与函数签名，核心业务逻辑后续逐步实现。
