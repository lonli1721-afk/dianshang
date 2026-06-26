from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from urllib.parse import urljoin

import httpx


logger = logging.getLogger("toapis")

DEFAULT_BASE_URL = "https://toapis.com"
SUPPORTED_MODELS = {"veo3.1-fast", "veo3.1-lite", "veo3.1-quality"}
SUPPORTED_ASPECT_RATIOS = {"16:9", "9:16"}


def _normalize_base_url(base_url: str = "") -> str:
    value = (base_url or "").strip().rstrip("/")
    return value or DEFAULT_BASE_URL


def _join_url(base_url: str, path: str) -> str:
    normalized = _normalize_base_url(base_url)
    clean_path = path.lstrip("/")
    if normalized.endswith("/v1") and clean_path.startswith("v1/"):
        clean_path = clean_path[3:]
    return urljoin(f"{normalized}/", clean_path)


def _normalize_aspect_ratio(value: str) -> str:
    raw = (value or "").strip()
    return raw if raw in SUPPORTED_ASPECT_RATIOS else "9:16"


def _toapis_error_message(status_code: int, body: str) -> str:
    detail = (body or "").strip()[:800]
    try:
        data = httpx.Response(status_code, content=body).json()
        detail = (
            data.get("error")
            or data.get("message")
            or data.get("msg")
            or data.get("detail")
            or detail
        )
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("msg") or str(detail)
    except Exception:
        pass
    if status_code in (401, 403):
        return f"ToAPIs API Key 无效或权限不足：{detail}"
    if status_code == 429:
        return f"ToAPIs 请求触发限流：{detail}"
    if 500 <= status_code <= 599:
        return f"ToAPIs 服务暂时不可用：{detail}"
    return f"ToAPIs 请求失败 ({status_code})：{detail}"


def _status_from_raw(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw in {"completed", "succeeded", "success", "finished", "done"}:
        return "completed"
    if raw in {"failed", "failure", "error", "cancelled", "canceled"}:
        return "failed"
    return "processing"


def _extract_task_id(data: dict) -> str:
    for key in ("id", "task_id", "generation_id", "request_id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    nested = data.get("data")
    if isinstance(nested, dict):
        return _extract_task_id(nested)
    return ""


def _extract_status(data: dict) -> str:
    for key in ("status", "state", "task_status"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    nested = data.get("data")
    if isinstance(nested, dict):
        return _extract_status(nested)
    return ""


def _extract_video_url(data: dict) -> str:
    for key in ("video_url", "url", "output_url", "result_url"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value

    for key in ("videos", "video_urls", "output", "results"):
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.startswith("http"):
                    return item
                if isinstance(item, dict):
                    found = _extract_video_url(item)
                    if found:
                        return found
        if isinstance(value, dict):
            found = _extract_video_url(value)
            if found:
                return found

    nested = data.get("data")
    if isinstance(nested, dict):
        return _extract_video_url(nested)
    return ""


def _extract_uploaded_image_url(data: dict) -> str:
    for key in ("url", "image_url", "file_url"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    nested = data.get("data")
    if isinstance(nested, dict):
        return _extract_uploaded_image_url(nested)
    return ""


class ToapisVideoService:
    def __init__(self, api_key: str, base_url: str = ""):
        self._api_key = api_key
        self._base_url = _normalize_base_url(base_url)

    def update(self, api_key: str, base_url: str = ""):
        self._api_key = api_key
        self._base_url = _normalize_base_url(base_url)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def upload_image_bytes(
        self,
        filename: str,
        content: bytes,
        mime_type: str = "image/png",
    ) -> str:
        if not content:
            raise Exception("ToAPIs 图片上传失败：图片内容为空")

        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.post(
                _join_url(self._base_url, "/v1/uploads/images"),
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": (filename or "image.png", content, mime_type or "image/png")},
            )
        if resp.status_code >= 400:
            raise Exception(_toapis_error_message(resp.status_code, resp.text))
        image_url = _extract_uploaded_image_url(resp.json())
        if not image_url:
            raise Exception(f"ToAPIs 图片上传未返回 URL：{str(resp.text)[:300]}")
        return image_url

    async def upload_image_path(self, filepath: Path) -> str:
        path = Path(filepath)
        if not path.exists():
            raise Exception(f"ToAPIs 图片上传失败：文件不存在 {path}")
        ext = path.suffix.lower().lstrip(".")
        mime_type = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }.get(ext, "image/png")
        content = await asyncio.to_thread(path.read_bytes)
        return await self.upload_image_bytes(path.name, content, mime_type)

    async def generate_video(
        self,
        prompt: str,
        model: str = "veo3.1-fast",
        aspect_ratio: str = "9:16",
        image_urls: list[str] | None = None,
        webhook_url: str = "",
    ) -> dict:
        model_id = model if model in SUPPORTED_MODELS else "veo3.1-fast"
        payload = {
            "model": model_id,
            "prompt": prompt,
            "duration": 8,
            "aspect_ratio": _normalize_aspect_ratio(aspect_ratio),
        }
        refs = [url for url in (image_urls or []) if url][:3]
        if refs:
            payload["image_urls"] = refs
        if webhook_url:
            payload["webhook_url"] = webhook_url

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.post(
                _join_url(self._base_url, "/v1/videos/generations"),
                headers=self._headers(),
                json=payload,
            )
        if resp.status_code >= 400:
            logger.error("ToAPIs create video error %d: %s", resp.status_code, resp.text[:800])
            raise Exception(_toapis_error_message(resp.status_code, resp.text))

        data = resp.json()
        task_id = _extract_task_id(data)
        if not task_id:
            raise Exception(f"ToAPIs 未返回任务 ID：{str(data)[:300]}")
        return {
            "task_id": task_id,
            "status": "processing",
            "provider": "toapis",
            "model": model_id,
            "duration": 8,
        }

    async def query_task(self, task_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(
                _join_url(self._base_url, f"/v1/videos/generations/{task_id}"),
                headers=self._headers(),
            )
        if resp.status_code >= 400:
            detail = _toapis_error_message(resp.status_code, resp.text)
            return {
                "task_id": task_id,
                "status": "failed",
                "video_url": "",
                "provider": "toapis",
                "error": detail,
            }

        data = resp.json()
        raw_status = _extract_status(data)
        status = _status_from_raw(raw_status)
        video_url = _extract_video_url(data)
        error = ""
        if status == "failed":
            error = str(data.get("error") or data.get("message") or data.get("msg") or "")[:500]
        return {
            "task_id": task_id,
            "status": status,
            "video_url": video_url,
            "provider": "toapis",
            "raw_status": raw_status,
            "error": error,
        }
