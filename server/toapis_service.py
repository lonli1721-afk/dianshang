from __future__ import annotations

import asyncio
import json
import logging
import random
from pathlib import Path
from urllib.parse import urljoin

import httpx

from video_model_registry import get_video_model_specs


logger = logging.getLogger("toapis")

DEFAULT_BASE_URL = "https://toapis.com"
SUPPORTED_ASPECT_RATIOS = {"16:9", "9:16", "3:2", "2:3", "1:1"}
TOAPIS_IMAGE_MODELS = [
    {
        "id": "image2",
        "name": "Image2",
        "provider": "toapis",
        "supports_ref_images": True,
        "max_ref_images": 16,
        "supported_qualities": ["1K", "2K", "4K"],
        "default_quality": "2K",
        "note": "通过 ToAPIs 官方渠道调用 GPT Image 2 / Image2。",
    },
]
TOAPIS_IMAGE_MAX_REFERENCE_IMAGES = 16


def _toapis_specs() -> list[dict]:
    return get_video_model_specs(provider_filter=["toapis"])


def _resolve_toapis_model(model: str) -> tuple[dict, str, str]:
    requested = (model or "").strip() or "veo3.1-fast"
    specs = _toapis_specs()
    for spec in specs:
        if requested in {spec.get("id"), spec.get("api_model")}:
            return spec, str(spec.get("id") or requested), str(spec.get("api_model") or requested)
    fallback = next((spec for spec in specs if spec.get("id") == "veo3.1-fast"), specs[0])
    return fallback, str(fallback.get("id") or "veo3.1-fast"), str(fallback.get("api_model") or fallback.get("id") or "veo3.1-fast")


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


def _normalize_image_model(value: str) -> str:
    raw = (value or "").strip()
    if not raw or raw == "image2":
        return "gpt-image-2"
    return raw


def _normalize_image_size(width: int = 1024, height: int = 1024, aspect_ratio: str = "") -> str:
    ratio = (aspect_ratio or "").strip()
    supported = {"1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16", "2:1", "1:2", "21:9", "9:21"}
    if ratio in supported:
        return ratio
    if width > height:
        value = width / max(1, height)
        if value >= 2.15:
            return "21:9"
        if value >= 1.9:
            return "2:1"
        if value >= 1.65:
            return "16:9"
        if value >= 1.42:
            return "3:2"
        if value >= 1.23:
            return "4:3"
        return "5:4"
    if height > width:
        value = height / max(1, width)
        if value >= 2.15:
            return "9:21"
        if value >= 1.9:
            return "1:2"
        if value >= 1.65:
            return "9:16"
        if value >= 1.42:
            return "2:3"
        if value >= 1.23:
            return "3:4"
        return "4:5"
    return "1:1"


def _normalize_image_resolution(value: str, size: str) -> str:
    raw = (value or "").strip().upper()
    requested = {"1K": "1k", "2K": "2k", "4K": "4k"}.get(raw, "2k")
    if requested == "1k" and size not in {"1:1", "3:2", "2:3"}:
        return "2k"
    if requested == "4k" and size not in {"4:3", "3:4", "16:9", "9:16", "2:1", "1:2", "21:9", "9:21"}:
        return "2k"
    return requested

def _normalize_resolution(value: str, spec: dict) -> str:
    raw = (value or "").strip().lower()
    supported = [str(item).lower() for item in (spec.get("supported_resolutions") or [])]
    if raw in supported:
        return raw
    default = str(spec.get("default_resolution") or "").lower()
    return default if default in supported else (supported[0] if supported else "720p")


def _normalize_duration(value: int | None, spec: dict) -> int:
    try:
        requested = int(value if value is not None else spec.get("max_duration") or 8)
    except (TypeError, ValueError):
        requested = int(spec.get("max_duration") or 8)
    choices = [int(item) for item in (spec.get("duration_choices") or [])]
    if choices:
        return min(choices, key=lambda item: abs(item - requested))
    min_duration = int(spec.get("min_duration") or 1)
    max_duration = int(spec.get("max_duration") or min_duration)
    return max(min_duration, min(requested, max_duration))


def _append_image_refs(payload: dict, refs: list[str], spec: dict) -> str:
    if not refs:
        return str(payload.get("prompt") or "")
    field = spec.get("toapis_ref_image_payload") or "image_urls"
    if field == "metadata_image_list":
        payload.setdefault("metadata", {})["image_list"] = [{"image_url": url} for url in refs]
        if spec.get("toapis_prompt_image_tokens"):
            prompt = str(payload.get("prompt") or "")
            if "<<<image_" not in prompt:
                token_text = " ".join(f"<<<image_{idx + 1}>>>" for idx in range(len(refs)))
                payload["prompt"] = f"{token_text} {prompt}".strip()
        return str(payload.get("prompt") or "")
    if field == "image_with_roles":
        payload["image_with_roles"] = [{"url": refs[0], "role": "first_frame"}]
        return str(payload.get("prompt") or "")
    if field in {"image_url", "image"}:
        payload[str(field)] = refs[0]
        return str(payload.get("prompt") or "")
    payload[str(field)] = refs
    return str(payload.get("prompt") or "")


def _extract_error_detail(data) -> str:
    if isinstance(data, str):
        return data.strip()[:800]
    if isinstance(data, list):
        for item in data:
            detail = _extract_error_detail(item)
            if detail:
                return detail
        return ""
    if not isinstance(data, dict):
        return ""

    for key in ("error", "message", "msg", "detail"):
        value = data.get(key)
        if isinstance(value, dict):
            code = value.get("code") or value.get("type") or ""
            message = value.get("message") or value.get("msg") or value.get("detail") or ""
            nested = _extract_error_detail(value)
            text = str(message or nested or value).strip()
            return (f"{code}: {text}" if code else text)[:800]
        if isinstance(value, str) and value.strip():
            return value.strip()[:800]

    for key in ("data", "result", "response"):
        detail = _extract_error_detail(data.get(key))
        if detail:
            return detail
    return ""


def _toapis_error_message(status_code: int, body: str) -> str:
    detail = (body or "").strip()[:800]
    try:
        data = httpx.Response(status_code, content=body).json()
        detail = _extract_error_detail(data) or detail
    except Exception:
        pass
    if status_code in (401, 403):
        return f"ToAPIs API Key 无效或权限不足：{detail}"
    if status_code == 429:
        return f"ToAPIs 请求触发限流：{detail}"
    if 500 <= status_code <= 599:
        return f"ToAPIs 服务暂时不可用：{detail}"
    return f"ToAPIs 请求失败 ({status_code})：{detail}"


def _toapis_network_error_message(exc: Exception) -> str:
    text = str(exc or "").strip()
    lowered = text.lower()
    if "server disconnected without sending a response" in lowered:
        return "ToAPIs 连接被上游断开：服务商或代理没有返回响应，请稍后重试。"
    if isinstance(exc, httpx.TimeoutException) or "timed out" in lowered or "timeout" in lowered:
        return "ToAPIs 请求超时：服务商或代理响应过慢，请稍后重试。"
    if isinstance(exc, httpx.ConnectError):
        return f"ToAPIs 连接失败：{text or '无法连接到服务商或代理'}"
    if isinstance(exc, httpx.TransportError):
        return f"ToAPIs 网络连接异常：{text or exc.__class__.__name__}"
    return text or exc.__class__.__name__


async def _toapis_request_with_retry(label: str, method: str, url: str, **kwargs) -> httpx.Response:
    last_exc: Exception | None = None
    timeout = kwargs.pop("timeout", None)
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                return await client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt >= 2:
                break
            wait = min(4.0, 0.8 * (2 ** attempt)) + random.uniform(0, 0.4)
            logger.warning("ToAPIs %s network error attempt=%s: %s", label, attempt + 1, str(exc)[:300])
            await asyncio.sleep(wait)
    raise Exception(_toapis_network_error_message(last_exc or Exception("unknown network error")))


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


def _redacted_payload_for_log(payload: dict) -> dict:
    safe = {}
    for key, value in payload.items():
        if key == "prompt":
            text = str(value or "")
            safe[key] = f"{text[:220]}..." if len(text) > 220 else text
        elif key in {"images", "image_urls", "reference_images"} and isinstance(value, list):
            safe[key] = [str(item)[:160] for item in value[:5]]
        elif key == "image_with_roles" and isinstance(value, list):
            safe[key] = [
                {"url": str(item.get("url") or "")[:160], "role": item.get("role")}
                if isinstance(item, dict) else str(item)[:160]
                for item in value[:5]
            ]
        elif key == "metadata" and isinstance(value, dict):
            image_list = value.get("image_list")
            safe[key] = {
                **{k: v for k, v in value.items() if k != "image_list"},
                "image_list": image_list[:5] if isinstance(image_list, list) else image_list,
            }
        else:
            safe[key] = value
    return safe


def _extract_video_url(data) -> str:
    if isinstance(data, str):
        value = data.strip()
        if value.startswith("http"):
            return value
        if value.startswith("{") or value.startswith("["):
            try:
                return _extract_video_url(json.loads(value))
            except (json.JSONDecodeError, TypeError):
                return ""
        return ""

    if isinstance(data, list):
        for item in data:
            found = _extract_video_url(item)
            if found:
                return found
        return ""

    if not isinstance(data, dict):
        return ""

    for key in ("video_url", "url", "output_url", "result_url"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
        found = _extract_video_url(value)
        if found:
            return found

    for key in ("result", "data", "videos", "video_urls", "output", "outputs", "results", "items"):
        value = data.get(key)
        found = _extract_video_url(value)
        if found:
            return found

    for key, value in data.items():
        key_l = str(key).lower()
        if any(token in key_l for token in ("video", "url", "result", "output")):
            found = _extract_video_url(value)
            if found:
                return found
    return ""


def _extract_image_url(data) -> str:
    if isinstance(data, str):
        value = data.strip()
        if value.startswith("http"):
            return value
        if value.startswith("{") or value.startswith("["):
            try:
                return _extract_image_url(json.loads(value))
            except (json.JSONDecodeError, TypeError):
                return ""
        return ""

    if isinstance(data, list):
        for item in data:
            found = _extract_image_url(item)
            if found:
                return found
        return ""

    if not isinstance(data, dict):
        return ""

    for key in ("image_url", "url", "output_url", "result_url", "file_url"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
        found = _extract_image_url(value)
        if found:
            return found

    for key in ("result", "data", "images", "image_urls", "output", "outputs", "results", "items"):
        found = _extract_image_url(data.get(key))
        if found:
            return found

    for key, value in data.items():
        key_l = str(key).lower()
        if any(token in key_l for token in ("image", "url", "result", "output")):
            found = _extract_image_url(value)
            if found:
                return found
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

        resp = await _toapis_request_with_retry(
            "upload_image",
            "POST",
            _join_url(self._base_url, "/v1/uploads/images"),
            timeout=120,
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

    async def generate_image(
        self,
        prompt: str,
        model: str = "image2",
        width: int = 1024,
        height: int = 1024,
        aspect_ratio: str = "",
        reference_urls: list[str] | None = None,
        image_quality: str = "2K",
        output_format: str = "png",
        timeout: int = 120,
    ) -> dict:
        api_model = _normalize_image_model(model)
        refs = [url for url in (reference_urls or []) if url][:TOAPIS_IMAGE_MAX_REFERENCE_IMAGES]
        size = _normalize_image_size(width, height, aspect_ratio)
        payload = {
            "model": api_model,
            "prompt": prompt,
            "size": size,
            "resolution": _normalize_image_resolution(image_quality, size),
            "n": 1,
            "response_format": "url",
        }
        if refs:
            payload["reference_images"] = refs

        resp = await _toapis_request_with_retry(
            "create_image",
            "POST",
            _join_url(self._base_url, "/v1/images/generations"),
            timeout=60,
            headers=self._headers(),
            json=payload,
        )
        if resp.status_code >= 400:
            logger.error(
                "ToAPIs create image error %d payload=%s response=%s",
                resp.status_code,
                json.dumps(_redacted_payload_for_log(payload), ensure_ascii=False)[:1200],
                resp.text[:800],
            )
            raise Exception(_toapis_error_message(resp.status_code, resp.text))

        data = resp.json()
        image_url = _extract_image_url(data)
        if image_url:
            return {
                "images": [{"url": image_url, "mime_type": "image/png"}],
                "image_url": image_url,
                "provider": "toapis",
                "model": model or "image2",
                "api_model": api_model,
            }

        task_id = _extract_task_id(data)
        if not task_id:
            raise Exception(f"ToAPIs 未返回图片地址或任务 ID：{str(data)[:300]}")

        deadline = asyncio.get_event_loop().time() + max(30, timeout)
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(3)
            query = await self.query_image_task(task_id)
            if query.get("status") == "completed" and query.get("image_url"):
                return {
                    "images": [{"url": query["image_url"], "mime_type": "image/png"}],
                    "image_url": query["image_url"],
                    "provider": "toapis",
                    "model": model or "image2",
                    "api_model": api_model,
                    "task_id": task_id,
                }
            if query.get("status") == "failed":
                raise Exception(query.get("error") or "ToAPIs 图片生成失败")
        raise Exception(f"ToAPIs 图片生成超时，任务 ID：{task_id}")

    async def query_image_task(self, task_id: str) -> dict:
        resp = await _toapis_request_with_retry(
            "query_image_task",
            "GET",
            _join_url(self._base_url, f"/v1/images/generations/{task_id}"),
            timeout=30,
            headers=self._headers(),
        )
        if resp.status_code >= 400:
            return {
                "task_id": task_id,
                "status": "failed",
                "image_url": "",
                "provider": "toapis",
                "error": _toapis_error_message(resp.status_code, resp.text),
            }
        data = resp.json()
        raw_status = _extract_status(data)
        status = _status_from_raw(raw_status)
        image_url = _extract_image_url(data)
        error = _extract_error_detail(data)[:500] if status == "failed" else ""
        return {
            "task_id": task_id,
            "status": status,
            "image_url": image_url,
            "provider": "toapis",
            "raw_status": raw_status,
            "error": error,
        }

    async def generate_video(
        self,
        prompt: str,
        model: str = "veo3.1-fast",
        aspect_ratio: str = "9:16",
        duration: int | None = None,
        resolution: str = "720p",
        image_urls: list[str] | None = None,
        webhook_url: str = "",
        generate_audio: bool = True,
    ) -> dict:
        spec, model_id, api_model = _resolve_toapis_model(model)
        normalized_duration = _normalize_duration(duration, spec)
        normalized_resolution = _normalize_resolution(resolution, spec)
        payload = {
            "model": api_model,
            "prompt": prompt,
        }
        duration_field = str(spec.get("toapis_duration_payload") or "duration")
        payload[duration_field] = str(normalized_duration) if duration_field == "seconds" else normalized_duration

        aspect_field = str(spec.get("toapis_aspect_payload") or "aspect_ratio")
        payload[aspect_field] = _normalize_aspect_ratio(aspect_ratio)

        if spec.get("toapis_mode_from_resolution"):
            payload["mode"] = "pro" if normalized_resolution == "1080p" else "std"
        elif normalized_resolution:
            payload["resolution"] = normalized_resolution

        refs = [url for url in (image_urls or []) if url][:int(spec.get("max_ref_images") or 0 or 3)]
        _append_image_refs(payload, refs, spec)
        if refs and spec.get("toapis_ref_task_type"):
            payload["task_type"] = str(spec["toapis_ref_task_type"])
        if webhook_url:
            payload["webhook_url"] = webhook_url
        if not generate_audio:
            payload["generate_audio"] = False
            payload["audio"] = False

        resp = await _toapis_request_with_retry(
            "create_video",
            "POST",
            _join_url(self._base_url, "/v1/videos/generations"),
            timeout=60,
            headers=self._headers(),
            json=payload,
        )
        if resp.status_code >= 400:
            logger.error(
                "ToAPIs create video error %d payload=%s response=%s",
                resp.status_code,
                json.dumps(_redacted_payload_for_log(payload), ensure_ascii=False)[:1200],
                resp.text[:800],
            )
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
            "api_model": api_model,
            "duration": normalized_duration,
        }

    async def query_task(self, task_id: str) -> dict:
        resp = await _toapis_request_with_retry(
            "query_task",
            "GET",
            _join_url(self._base_url, f"/v1/videos/generations/{task_id}"),
            timeout=30,
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
            error = _extract_error_detail(data)[:500]
        if status == "completed" and not video_url:
            logger.warning("ToAPIs task %s completed without extracted video URL: %s", task_id, str(data)[:1200])
        return {
            "task_id": task_id,
            "status": status,
            "video_url": video_url,
            "provider": "toapis",
            "raw_status": raw_status,
            "error": error,
        }
