from __future__ import annotations

"""
阿里云百炼 HappyHorse 视频生成服务。

当前接入范围：
- happyhorse-1.0-t2v 文生视频
- happyhorse-1.0-i2v 首帧图生视频
- happyhorse-1.0-r2v 参考图生视频
- happyhorse-1.0-video-edit 视频编辑

官方文档：
- https://help.aliyun.com/zh/model-studio/happyhorse-text-to-video-api-reference
- https://help.aliyun.com/zh/model-studio/happyhorse-image-to-video-api-reference
- https://help.aliyun.com/zh/model-studio/happyhorse-reference-to-video-api-reference
- https://www.alibabacloud.com/help/doc-detail/3030779.html
"""

import asyncio
import logging

import httpx

logger = logging.getLogger("happyhorse")

BASE_URL = "https://dashscope.aliyuncs.com/api/v1"

TEXT_TO_VIDEO_MODELS = {"happyhorse-1.0-t2v"}
IMAGE_TO_VIDEO_MODELS = {"happyhorse-1.0-i2v"}
REFERENCE_TO_VIDEO_MODELS = {"happyhorse-1.0-r2v"}
VIDEO_EDIT_MODELS = {"happyhorse-1.0-video-edit"}
SUPPORTED_MODELS = TEXT_TO_VIDEO_MODELS | IMAGE_TO_VIDEO_MODELS | REFERENCE_TO_VIDEO_MODELS | VIDEO_EDIT_MODELS
SUPPORTED_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4"}
SUPPORTED_RESOLUTIONS = {"720P", "1080P"}

_HAPPYHORSE_ERROR_ZH: list[tuple[str, str]] = [
    ("Arrearage", "阿里云账号已欠费，请前往控制台充值后重试。"),
    ("overdue-payment", "阿里云账号已欠费，请前往控制台充值后重试。"),
    ("good standing", "访问被拒绝：阿里云账号可能欠费或未开通 HappyHorse 服务，请检查百炼视频模型权限。"),
    ("Access denied", "访问被拒绝：阿里云账号可能欠费或未开通 HappyHorse 服务，请检查百炼视频模型权限。"),
    ("InvalidApiKey", "DashScope API Key 无效：请检查阿里云百炼 API Key 是否正确。"),
    ("Throttling", "请求过于频繁，已触发限流。请稍后再试。"),
    ("DataInspectionFailed", "内容安全审核未通过：请更换提示词或素材后再试。"),
    ("IPInfringementSuspect", "内容安全：疑似版权或不当内容，请更换素材。"),
    ("InvalidParameter", "请求参数无效：请检查 HappyHorse 的时长、比例、分辨率和参考图要求。"),
    ("InvalidImage", "参考图无效：请检查图片格式、尺寸、比例和公网可访问性。"),
    ("InvalidVideo", "参考视频无效：请使用 3～60 秒、MP4/MOV、分辨率和大小符合文档要求的视频。"),
    ("Unable to download the media resource", "无法下载参考图：请确认图片公网链接可访问，且格式符合要求。"),
]


def _normalize_resolution(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "720P"
    normalized = raw.upper()
    if normalized in SUPPORTED_RESOLUTIONS:
        return normalized
    return "720P"


def _normalize_ratio(value: str) -> str:
    raw = (value or "").strip()
    if raw in SUPPORTED_RATIOS:
        return raw
    return "9:16"


def _localize_happyhorse_error(message: str, code: str = "") -> str:
    raw = (message or "").strip()
    blob = f"[{code}] {raw}" if code else raw
    if not blob:
        return "HappyHorse 服务返回未知错误，请稍后重试。"
    for key, zh in _HAPPYHORSE_ERROR_ZH:
        if key in blob or key in raw:
            return zh
    return f"HappyHorse 服务错误：{raw}" if raw else f"HappyHorse 服务错误（{code}）"


def _extract_dashscope_video_url(output: dict, raw: dict | None = None) -> str:
    """兼容 DashScope/HappyHorse 不同完成结果里的视频地址字段。"""
    results = output.get("results")
    if isinstance(results, dict):
        for key in ("video_url", "url", "output_url", "result_url"):
            value = results.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            for key in ("video_url", "url", "output_url", "result_url"):
                value = item.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value
    for key in ("video_url", "output_url", "result_url", "url"):
        value = output.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    if raw:
        for key in ("video_url", "output_url", "result_url", "url"):
            value = raw.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
    return ""


class HappyHorseService:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def update_key(self, api_key: str):
        self._api_key = api_key

    def _headers(self, async_mode: bool = False) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if async_mode:
            headers["X-DashScope-Async"] = "enable"
        return headers

    async def text_to_video(
        self,
        prompt: str,
        model: str = "happyhorse-1.0-t2v",
        duration: int = 5,
        resolution: str = "720p",
        aspect_ratio: str = "9:16",
    ) -> dict:
        model_id = model if model in TEXT_TO_VIDEO_MODELS else "happyhorse-1.0-t2v"
        clamped_duration = max(3, min(int(duration or 5), 15))
        payload = {
            "model": model_id,
            "input": {"prompt": prompt},
            "parameters": {
                "resolution": _normalize_resolution(resolution),
                "ratio": _normalize_ratio(aspect_ratio),
                "duration": clamped_duration,
            },
        }
        return await self._create_task(payload)

    async def image_to_video(
        self,
        image_url: str,
        prompt: str = "",
        model: str = "happyhorse-1.0-i2v",
        duration: int = 5,
        resolution: str = "720p",
    ) -> dict:
        if not image_url:
            raise Exception("HappyHorse 首帧图生视频需要至少 1 张参考图。")
        model_id = model if model in IMAGE_TO_VIDEO_MODELS else "happyhorse-1.0-i2v"
        clamped_duration = max(3, min(int(duration or 5), 15))
        payload = {
            "model": model_id,
            "input": {
                "prompt": prompt or "",
                "media": [
                    {
                        "type": "first_frame",
                        "url": image_url,
                    }
                ],
            },
            "parameters": {
                "resolution": _normalize_resolution(resolution),
                "duration": clamped_duration,
            },
        }
        return await self._create_task(payload)

    async def reference_to_video(
        self,
        reference_images: list[str],
        prompt: str,
        model: str = "happyhorse-1.0-r2v",
        duration: int = 5,
        resolution: str = "720p",
        aspect_ratio: str = "9:16",
    ) -> dict:
        refs = [url for url in reference_images if url][:9]
        if not refs:
            raise Exception("HappyHorse 参考图生视频需要至少 1 张参考图。")
        model_id = model if model in REFERENCE_TO_VIDEO_MODELS else "happyhorse-1.0-r2v"
        clamped_duration = max(3, min(int(duration or 5), 15))
        payload = {
            "model": model_id,
            "input": {
                "prompt": prompt,
                "media": [{"type": "reference_image", "url": url} for url in refs],
            },
            "parameters": {
                "resolution": _normalize_resolution(resolution),
                "ratio": _normalize_ratio(aspect_ratio),
                "duration": clamped_duration,
            },
        }
        return await self._create_task(payload)

    async def edit_video(
        self,
        video_url: str,
        prompt: str,
        reference_images: list[str] | None = None,
        model: str = "happyhorse-1.0-video-edit",
        resolution: str = "720p",
    ) -> dict:
        if not video_url:
            raise Exception("HappyHorse 视频编辑需要 1 个参考视频。")
        model_id = model if model in VIDEO_EDIT_MODELS else "happyhorse-1.0-video-edit"
        media = [{"type": "video", "url": video_url}]
        for url in (reference_images or [])[:5]:
            if url:
                media.append({"type": "reference_image", "url": url})
        payload = {
            "model": model_id,
            "input": {
                "prompt": prompt,
                "media": media,
            },
            "parameters": {
                "resolution": _normalize_resolution(resolution),
            },
        }
        return await self._create_task(payload)

    async def _create_task(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE_URL}/services/aigc/video-generation/video-synthesis",
                headers=self._headers(async_mode=True),
                json=payload,
            )
        if resp.status_code >= 400:
            body = resp.text[:800]
            logger.error("HappyHorse create task error %d: %s", resp.status_code, body)
            message = body
            code = ""
            try:
                data = resp.json()
                message = data.get("message", data.get("msg", "")) or body[:300]
                code = data.get("code", "") or ""
            except Exception:
                pass
            raise Exception(_localize_happyhorse_error(message, code))

        data = resp.json()
        output = data.get("output", {})
        task_id = output.get("task_id", "")
        if not task_id:
            raise Exception(f"HappyHorse 未返回任务编号，请稍后重试。接口返回：{str(data)[:200]}")
        return {"task_id": task_id, "status": "processing", "provider": "happyhorse"}

    async def query_task(self, task_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/tasks/{task_id}",
                headers=self._headers(),
            )
        if resp.status_code >= 400:
            detail = resp.text[:300]
            logger.error("HappyHorse query task error %d for %s: %s", resp.status_code, task_id, detail)
            return {
                "task_id": task_id,
                "status": "failed",
                "video_url": "",
                "provider": "happyhorse",
                "error": f"查询任务失败 ({resp.status_code}): {detail}",
            }

        data = resp.json()
        output = data.get("output", {})
        raw_status = output.get("task_status", "UNKNOWN")
        video_url = _extract_dashscope_video_url(output, data)
        error = ""
        if raw_status in ("FAILED", "CANCELED"):
            code = output.get("code", "") or data.get("code", "")
            message = output.get("message", "") or data.get("message", "")
            error = _localize_happyhorse_error(message, code)

        mapped = {
            "SUCCEEDED": "completed",
            "FAILED": "failed",
            "CANCELED": "failed",
            "PENDING": "processing",
            "RUNNING": "processing",
            "UNKNOWN": "processing",
        }.get(raw_status, "processing")

        return {
            "task_id": task_id,
            "status": mapped,
            "video_url": video_url,
            "provider": "happyhorse",
            "raw_status": raw_status,
            "error": error,
        }

    async def wait_for_video(self, task_id: str, timeout: int = 600, interval: int = 10) -> dict:
        elapsed = 0
        while elapsed < timeout:
            result = await self.query_task(task_id)
            if result["status"] in ("completed", "failed"):
                return result
            await asyncio.sleep(interval)
            elapsed += interval
        return {"task_id": task_id, "status": "timeout", "video_url": "", "provider": "happyhorse"}
