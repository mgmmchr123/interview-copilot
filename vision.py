from __future__ import annotations

import os
import time
from typing import Callable

import config
import llm

TokenCallback = Callable[[str], None]


def capture_photo() -> str | None:
    """
    用 opencv 打开摄像头，显示预览窗口。

    - 空格键拍照并保存到 config.PHOTOS_DIR
    - ESC 取消
    - 返回照片路径；取消/失败返回 None
    """
    try:
        import cv2
    except Exception as exc:
        print(f"[vision] OpenCV 未安装或导入失败: {exc}")
        return None

    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    if not cap.isOpened():
        print(
            f"[vision] Cannot open camera index {config.CAMERA_INDEX}, "
            "try changing CAMERA_INDEX in config.py"
        )
        return None

    print("[vision] Camera open - SPACE to capture, ESC to cancel")
    window_name = "Camera - SPACE to capture, ESC to cancel"

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1)

            if key == 32:  # 空格键拍照
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                os.makedirs(config.PHOTOS_DIR, exist_ok=True)
                save_path = os.path.join(config.PHOTOS_DIR, f"photo_{timestamp}.jpg")
                cv2.imwrite(save_path, frame)
                print(f"[vision] Photo saved: {save_path}")
                return save_path
            if key == 27:  # ESC 取消
                return None
    except Exception as exc:
        print(f"[vision] capture_photo 失败: {exc}")
        return None
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return None


def analyze_image(image_path: str, on_token: TokenCallback | None = None) -> str:
    """调用 llm.analyze_image 分析图片，支持 streaming 回调透传。"""
    try:
        return llm.analyze_image(image_path, on_token=on_token)
    except Exception as exc:
        print(f"[vision] analyze_image 调用失败: {exc}")
        return ""


if __name__ == "__main__":
    print("=== Vision 测试：OpenCV 拍照并分析 ===")
    captured = capture_photo()
    if not captured:
        print("未拍照或已取消，测试结束。")
    else:
        print(f"照片路径: {captured}")
        print("开始调用视觉分析（流式输出）：")

        def _printer(token: str) -> None:
            print(token, end="", flush=True)

        result = analyze_image(captured, on_token=_printer)
        print("\n\n最终分析结果:")
        print(result if result else "(空字符串)")
