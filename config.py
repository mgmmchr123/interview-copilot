import os

print("🔥 UI FILE LOADED")
# 已确认配置
AUDIO_DEVICE_INDEX = 7
WHISPER_MODEL = "small"
WHISPER_LANGUAGE = "en"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_BEAM_SIZE = 1
WHISPER_HOTWORDS = [
    "JIT compiler",
    "pointer",
    "binary tree",
    "hash map",
    "linked list",
    "recursion",
    "dynamic programming",
    "Big O notation",
    "REST API",
    "async",
    "thread",
    "mutex",
    "deadlock",
    "heap",
    "stack",
    "garbage collection",
    "polymorphism",
    "inheritance",
    "interface",
    "microservices",
    "Docker",
    "Kubernetes",
    "SQL",
    "NoSQL",
    "JRE",
    "JVM",
    "JDK",
    "platform independent",
    "bytecode",
    "interpreter",
    "runtime",
    "classpath",
    "generics",
    "lambda",
    "multithreading",
    "synchronization",
    "object oriented",
    "design pattern",
    "singleton",
    "factory",
    "observer",
]
CHUNK_SECONDS = 4

LLM_PROVIDER = "ollama"
LLM_MODEL = "qwen2.5:14b"
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_VISION_MODEL = "qwen3-vl:8b"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CAMERA_INDEX = 1  # 0 = 内建摄像头，1 = 外接 USB 摄像头
PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "photos")
# 照片存在项目目录下的 photos 文件夹，完全本地

UI_WIDTH = 360
UI_HEIGHT = 550
UI_OPACITY = 0.92
