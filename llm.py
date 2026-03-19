import base64
import json
import mimetypes
from pathlib import Path
from typing import Callable

import requests

import config

TokenCallback = Callable[[str], None]

INTERVIEW_FILTER_PROMPT = """你需要先判断用户输入是否是“面试问题”。
只有以下类型才是面试问题需要回答：
- 行为题（Tell me about, How did you, Describe a time）
- 技术概念题（What is, How does, Explain）
- 代码/算法题（Implement, Write a function, What is the complexity）
- 系统设计题（Design a system, How would you architect）
闲聊、感谢、过渡语句不是面试问题，直接返回空字符串。"""

ANSWER_SYSTEM_PROMPT = """You are a senior backend engineer answering interview questions.

Respond in 3 parts:

1. One-line definition (simple)
2. Real-world example (short)
3. Key trade-off or failure case

Keep answer under 120 words.
Use bullet points if helpful.
Sound natural and concise."""

VISION_USER_PROMPT = (
    "请分析这张图片中可能的面试题内容，并给出简洁的解题思路。"
    "输出要点化，控制在 150 字以内。"
)


def _safe_emit(token: str, on_token: TokenCallback | None) -> None:
    """安全触发 token 回调，避免回调异常影响主流程。"""
    if not token or on_token is None:
        return
    try:
        on_token(token)
    except Exception as exc:
        print(f"[llm] on_token 回调异常: {exc}")


def _looks_like_interview_question(text: str) -> bool:
    """基于关键词的快速过滤，避免对闲聊调用 API。"""
    normalized = text.strip().lower()
    if not normalized:
        return False

    interview_starts = (
        "tell me about",
        "how did you",
        "describe a time",
        "what is",
        "how does",
        "explain",
        "implement",
        "write a function",
        "what is the complexity",
        "design a system",
        "how would you architect",
    )
    interview_keywords = (
        "complexity",
        "algorithm",
        "data structure",
        "system design",
        "architecture",
        "thread",
        "mutex",
        "api",
        "database",
    )
    non_question_phrases = (
        "okay",
        "thanks",
        "thank you",
        "let's move on",
        "sounds good",
        "got it",
    )

    if any(phrase in normalized for phrase in non_question_phrases):
        if not any(word in normalized for word in interview_keywords):
            return False

    if normalized.startswith(interview_starts):
        return True

    if "?" in normalized and any(word in normalized for word in interview_keywords):
        return True

    return any(word in normalized for word in interview_keywords)


def _read_image_base64(image_path: str) -> tuple[str, str]:
    """读取图片并返回 (mime_type, base64_data)。"""
    path = Path(image_path)
    raw = path.read_bytes()
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    b64_data = base64.b64encode(raw).decode("utf-8")
    return mime_type, b64_data


def _call_anthropic(
    prompt: str, image_path: str | None = None, on_token: TokenCallback | None = None
) -> str:
    """Anthropic 调用：支持文本与图片，使用流式输出。"""
    if not config.ANTHROPIC_API_KEY:
        print("[llm] 缺少 ANTHROPIC_API_KEY，跳过调用。")
        return ""

    try:
        from anthropic import Anthropic
    except Exception as exc:
        print(f"[llm] 未安装 anthropic SDK: {exc}")
        return ""

    try:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        content: list[dict] = [{"type": "text", "text": prompt}]
        if image_path:
            media_type, b64_data = _read_image_base64(image_path)
            content.insert(
                0,
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64_data,
                    },
                },
            )

        final_text = ""
        with client.messages.stream(
            model=config.LLM_MODEL,
            max_tokens=512,
            system=ANSWER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    token = getattr(delta, "text", "") if delta else ""
                    if token:
                        final_text += token
                        _safe_emit(token, on_token)
        return final_text.strip()
    except Exception as exc:
        print(f"[llm] Anthropic 调用失败: {exc}")
        return ""


def _call_ollama(
    prompt: str, image_path: str | None = None, on_token: TokenCallback | None = None
) -> str:
    """Ollama 调用：requests + /api/generate 流式逐行解析。"""
    model = config.OLLAMA_VISION_MODEL if image_path else config.LLM_MODEL
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "system": ANSWER_SYSTEM_PROMPT,
        "stream": True,
    }

    if image_path:
        _, b64_data = _read_image_base64(image_path)
        payload["images"] = [b64_data]

    try:
        response = requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json=payload,
            stream=True,
            timeout=180,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("[llm] Ollama 连接失败，请确认 ollama serve 已启动")
        return ""
    except Exception as exc:
        print(f"[llm] Ollama 请求失败: {exc}")
        return ""

    final_text = ""
    try:
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            print("RAW:", line)
            item = json.loads(line)
            token = (
                item.get("response")
                or item.get("content")
                or (
                    item.get("message", {}).get("content")
                    if item.get("message")
                    else ""
                )
            )
            if token:
                final_text += token
                _safe_emit(token, on_token)
            if item.get("done", False):
                break
    except Exception as exc:
        print(f"[llm] Ollama 流解析失败: {exc}")
        return ""
    return final_text.strip()


def _call_openai(
    prompt: str, image_path: str | None = None, on_token: TokenCallback | None = None
) -> str:
    """OpenAI 调用占位。"""
    if not config.OPENAI_API_KEY:
        print("[llm] 缺少 OPENAI_API_KEY，跳过调用。")
        return ""
    raise NotImplementedError("TODO: implement _call_openai")


def _call_gemini(
    prompt: str, image_path: str | None = None, on_token: TokenCallback | None = None
) -> str:
    """Gemini 调用占位。"""
    raise NotImplementedError("TODO: implement _call_gemini")


def _call_provider(
    prompt: str, image_path: str | None = None, on_token: TokenCallback | None = None
) -> str:
    """根据配置选择 provider。"""
    provider = config.LLM_PROVIDER.strip().lower()
    try:
        if provider == "ollama":
            return _call_ollama(prompt, image_path=image_path, on_token=on_token)
        if provider == "anthropic":
            return _call_anthropic(prompt, image_path=image_path, on_token=on_token)
        if provider == "openai":
            return _call_openai(prompt, image_path=image_path, on_token=on_token)
        if provider == "gemini":
            return _call_gemini(prompt, image_path=image_path, on_token=on_token)
        print(f"[llm] 不支持的 LLM_PROVIDER: {config.LLM_PROVIDER}")
        return ""
    except NotImplementedError as exc:
        print(f"[llm] 功能未实现: {exc}")
        return ""
    except Exception as exc:
        print(f"[llm] Provider 调用失败: {exc}")
        return ""


def analyze_text(text: str, on_token: TokenCallback | None = None) -> str:
    """分析文本：若是面试问题则生成答案；否则返回空字符串。"""
    try:
        content = text.strip()
        # DEBUG: 临时关闭过滤，确认 LLM 调用链路是否正常
        # if not _looks_like_interview_question(content):
        #     return ""
        print("[llm] calling LLM with:", content)

        prompt = f"Answer this interview question:\n{content}"
        return _call_provider(prompt, image_path=None, on_token=on_token)
    except Exception as exc:
        print(f"[llm] analyze_text 失败: {exc}")
        return ""


def analyze_image(image_path: str, on_token: TokenCallback | None = None) -> str:
    """分析图片：将图片发给视觉模型并输出解题思路。"""
    try:
        path = Path(image_path)
        if not path.exists():
            print(f"[llm] 图片不存在: {image_path}")
            return ""
        prompt = (
            f"{INTERVIEW_FILTER_PROMPT}\n\n"
            f"{VISION_USER_PROMPT}\n"
            "如果图中不是面试题场景，可返回空字符串。"
        )
        return _call_provider(prompt, image_path=image_path, on_token=on_token)
    except Exception as exc:
        print(f"[llm] analyze_image 失败: {exc}")
        return ""


def _find_test_image() -> str | None:
    """从摄像头目录中找一张可测试图片。"""
    watch_dir = Path(config.CAMERA_WATCH_FOLDER)
    if not watch_dir.exists():
        return None
    candidates = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"):
        candidates.extend(watch_dir.glob(ext))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(candidates[0])


if __name__ == "__main__":
    def _stream_printer(token: str) -> None:
        print(token, end="", flush=True)


    print("=== 测试1：文字面试问题 ===")
    question = "What is JIT compiler?"
    print(f"输入: {question}")
    print("流式输出: ", end="", flush=True)
    result1 = analyze_text(question, on_token=_stream_printer)
    print("\n最终结果:", result1)

    print("\n=== 测试2：非面试问题过滤 ===")
    small_talk = "okay, so let's move on"
    print(f"输入: {small_talk}")
    print("流式输出: ", end="", flush=True)
    result2 = analyze_text(small_talk, on_token=_stream_printer)
    print("\n最终结果:", result2 if result2 else "(空字符串，已过滤)")

    print("\n=== 测试3：图片分析 ===")
    test_image = _find_test_image()
    if test_image:
        print(f"使用图片: {test_image}")
        print("流式输出: ", end="", flush=True)
        result3 = analyze_image(test_image, on_token=_stream_printer)
        print("\n最终结果:", result3 if result3 else "(空字符串)")
    else:
        print("未找到可用摄像头图片，跳过测试3。")
