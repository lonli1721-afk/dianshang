from __future__ import annotations

"""
VIDU 视频生成服务。
官方文档: https://docs.platform.vidu.cn

模型: viduq3-pro (最新, 1-16s), viduq3-turbo (1-16s), viduq2 (1-10s), viduq1 (5s)
图生视频模型: viduq3-pro, viduq3-turbo, viduq2-pro-fast, viduq2-pro, viduq2-turbo
"""

import asyncio
import base64
import io
import httpx
import logging
from typing import Optional

logger = logging.getLogger("vidu")

MAX_B64_BYTES = 10 * 1024 * 1024  # VIDU limit: base64 decoded < 10MB


def _compress_base64_image(data_url: str) -> str:
    """If a base64 data URL image exceeds VIDU's size limit, compress it."""
    if not data_url.startswith("data:image"):
        return data_url
    try:
        header, b64data = data_url.split(",", 1)
        raw = base64.b64decode(b64data)
        if len(raw) <= MAX_B64_BYTES:
            return data_url
        logger.info("Image too large for VIDU (%d bytes), compressing...", len(raw))
        try:
            from PIL import Image
        except ImportError:
            logger.warning("Pillow not installed, skipping compression")
            return data_url
        img = Image.open(io.BytesIO(raw))
        if img.mode == "RGBA":
            img = img.convert("RGB")
        w, h = img.size
        scale = (MAX_B64_BYTES / len(raw)) ** 0.5 * 0.9
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        compressed = buf.getvalue()
        logger.info("Compressed: %d -> %d bytes (%dx%d)", len(raw), len(compressed), int(w * scale), int(h * scale))
        return f"data:image/jpeg;base64,{base64.b64encode(compressed).decode()}"
    except Exception as e:
        logger.warning("Image compression failed: %s", e)
        return data_url

BASE_URL = "https://api.vidu.cn"

TEXT2VIDEO_MODELS = {
    "viduq3-pro":  "viduq3-pro",
    "viduq3-turbo": "viduq3-turbo",
    "viduq2":      "viduq2",
    "viduq1":      "viduq1",
}

IMG2VIDEO_MODELS = {
    "viduq3-pro":      "viduq3-pro",
    "viduq3-turbo":    "viduq3-turbo",
    "viduq2-pro-fast": "viduq2-pro-fast",
    "viduq2-pro":      "viduq2-pro",
    "viduq2-turbo":    "viduq2-turbo",
}

DURATION_LIMITS = {
    "viduq3-pro": (1, 16),
    "viduq3-turbo": (1, 16),
    "viduq2-pro-fast": (1, 10),
    "viduq2-pro": (1, 10),
    "viduq2-turbo": (1, 10),
    "viduq2": (1, 10),
    "viduq1": (5, 5),
}


class ViduService:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }

    def update_key(self, api_key: str):
        self._api_key = api_key
        self._headers["Authorization"] = f"Token {api_key}"

    async def text_to_video(
        self,
        prompt: str,
        model: str = "viduq3-pro",
        duration: int = 5,
        resolution: str = "720p",
        aspect_ratio: str = "9:16",
        style: str = "general",
        movement_amplitude: str = "auto",
    ) -> dict:
        model_id = TEXT2VIDEO_MODELS.get(model, "viduq3-pro")
        min_d, max_d = DURATION_LIMITS.get(model_id, (1, 16))
        clamped = max(min_d, min(duration, max_d))
        payload = {
            "model": model_id,
            "prompt": prompt,
            "duration": clamped,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "style": style,
            "movement_amplitude": movement_amplitude,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE_URL}/ent/v2/text2video",
                headers=self._headers,
                json=payload,
            )
            if resp.status_code >= 400:
                detail = resp.text[:500]
                raise Exception(f"VIDU text2video 请求失败 ({resp.status_code}): {detail}")
            data = resp.json()

        task_id = data.get("task_id", data.get("id", ""))
        return {"task_id": task_id, "status": "processing", "provider": "vidu"}

    async def image_to_video(
        self,
        image_url: str,
        prompt: str = "",
        model: str = "viduq3-pro",
        duration: int = 5,
        resolution: str = "720p",
        movement_amplitude: str = "auto",
    ) -> dict:
        model_id = IMG2VIDEO_MODELS.get(model, "viduq3-pro")
        min_d, max_d = DURATION_LIMITS.get(model_id, (1, 16))
        clamped = max(min_d, min(duration, max_d))

        image_url = _compress_base64_image(image_url)
        img_type = "url" if image_url.startswith("http") else "base64" if image_url.startswith("data:") else "other"
        img_size = len(image_url) if img_type == "base64" else 0
        logger.info("VIDU img2video: model=%s, duration=%d, resolution=%s, image_type=%s, image_size=%dKB, prompt_len=%d",
                     model_id, clamped, resolution, img_type, img_size // 1024, len(prompt or ""))

        payload = {
            "model": model_id,
            "images": [image_url],
            "duration": clamped,
            "resolution": resolution,
            "movement_amplitude": movement_amplitude,
        }
        if prompt:
            payload["prompt"] = prompt

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE_URL}/ent/v2/img2video",
                headers=self._headers,
                json=payload,
            )
            if resp.status_code >= 400:
                detail = resp.text[:500]
                logger.error("VIDU img2video error %d: %s | payload keys=%s image_type=%s",
                             resp.status_code, detail, list(payload.keys()),
                             "url" if image_url.startswith("http") else "base64" if image_url.startswith("data:") else "other")
                raise Exception(f"VIDU img2video 请求失败 ({resp.status_code}): {detail}")
            data = resp.json()

        task_id = data.get("task_id", data.get("id", ""))
        logger.info("VIDU img2video task created: %s", task_id)
        return {"task_id": task_id, "status": "processing", "provider": "vidu"}

    async def query_task(self, task_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/ent/v2/tasks/{task_id}/creations",
                headers=self._headers,
            )
            if resp.status_code >= 400:
                detail = resp.text[:300]
                logger.error("VIDU query_task error %d for %s: %s", resp.status_code, task_id, detail)
                return {"task_id": task_id, "status": "failed", "video_url": "", "provider": "vidu",
                        "error": f"查询任务失败 ({resp.status_code}): {detail}"}
            data = resp.json()

        state = data.get("state", data.get("status", "processing"))
        err_code = data.get("err_code", "")
        video_url = ""
        creations = data.get("creations", data.get("data", []))
        if creations and isinstance(creations, list):
            for c in creations:
                url = c.get("url", c.get("video_url", ""))
                if url:
                    video_url = url
                    break

        mapped = "completed" if state in ("success", "succeeded") else "failed" if state == "failed" else "processing"

        if mapped == "failed":
            logger.warning("VIDU task %s failed: err_code=%s, raw=%s", task_id, err_code, str(data)[:300])

        error_msg = ""
        if err_code:
            ERR_MAP = {
                "ImageDownloadFailure": "VIDU无法下载参考图片，请检查图片是否可公开访问",
                "CreditInsufficient": "VIDU积分不足，请充值",
                "TaskPromptPolicyViolation": "提示词触发VIDU内容审核，请修改提示词",
                "AuditSubmitIllegal": "输入内容未通过VIDU安全审核",
                "CreationPolicyViolation": "生成内容触发VIDU风控",
                "ModelUnavailable": "VIDU模型暂不可用",
                "PageSizeOutOfRange": "图片尺寸不符合要求（需<50MB，比例<4:1）",
                "ImageFormatInvalid": "图片格式不符合要求（支持png/jpg/webp）",
            }
            error_msg = ERR_MAP.get(err_code, f"VIDU错误: {err_code}")

        return {
            "task_id": task_id,
            "status": mapped,
            "video_url": video_url,
            "provider": "vidu",
            "raw_status": state,
            "error": error_msg,
            "err_code": err_code,
        }

    async def wait_for_video(self, task_id: str, timeout: int = 600, interval: int = 8) -> dict:
        elapsed = 0
        while elapsed < timeout:
            result = await self.query_task(task_id)
            if result["status"] in ("completed", "failed"):
                return result
            await asyncio.sleep(interval)
            elapsed += interval
        return {"task_id": task_id, "status": "timeout", "video_url": "", "provider": "vidu"}
