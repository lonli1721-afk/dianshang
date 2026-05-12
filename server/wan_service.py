"""
万相 wan2.2-animate-mix 视频换人服务。

专用于视频人物替换：上传角色图片+参考视频，保持动作/表情/场景/光照不变，
仅替换视频中的人物。
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes

import httpx

logger = logging.getLogger("wan_service")

BASE_URL = "https://dashscope.aliyuncs.com/api/v1"

# 万相 / DashScope 常见错误码与英文说明 → 中文（便于前端直接展示）
_WAN_ERROR_ZH: list[tuple[str, str]] = [
    ("Access denied", "访问被拒绝：阿里云账号已欠费或未开通万相服务。请前往阿里云控制台充值或开通 DashScope 模型服务。"),
    ("overdue-payment", "访问被拒绝：阿里云账号已欠费，请前往阿里云控制台充值后重试。"),
    ("Arrearage", "阿里云账号已欠费，请前往控制台充值后重试。"),
    ("Throttling", "请求过于频繁，已触发限流。请稍后再试。"),
    ("InvalidApiKey", "API Key 无效：请检查 DashScope API Key 是否正确。"),
    ("InvalidImage.FileFormat", "图片格式无效：请上传有效的 JPG、PNG、JPEG、BMP 或 WEBP；若为 WebP/动图请先转为 PNG/JPEG。并确认公网地址能直接下载图片文件。"),
    ("InvalidImage.FullFace", "参考图人脸不符合要求：需正脸、完整、无遮挡的清晰人像，请换一张图重试。"),
    ("DataInspectionFailed", "内容安全审核未通过：图片或视频被判定存在风险内容，请更换素材后再试。"),
    ("IPInfringementSuspect", "内容安全：疑似版权或不当内容，请更换素材。"),
    ("InvalidParameter.DataInspection", "数据检测失败：阿里云无法下载或校验媒体资源，请检查公网 URL 是否可访问、格式是否正确。"),
    ("Unable to download the media resource", "无法下载媒体：请确认图片/视频的公网链接可访问，且已在安全组放行阿里云访问源 IP。"),
    ("InvalidParameter", "请求参数无效：请检查图片/视频地址与格式是否符合万相 API 要求。"),
    ("InvalidVideo", "参考视频无效：请使用 2～30 秒、MP4/MOV、比例与大小符合文档要求的视频。"),
    ("InvalidImage", "参考图片无效：请检查格式、尺寸与内容是否符合万相要求。"),
]


def localize_wan_error(message: str, code: str = "") -> str:
    """将万相返回的英文/错误码说明转为中文；未知错误保留原文并加前缀。"""
    raw = (message or "").strip()
    blob = f"[{code}] {raw}" if code else raw
    if not blob.strip():
        return "万相服务返回未知错误，请稍后重试。"
    for key, zh in _WAN_ERROR_ZH:
        if key in blob or key in raw:
            return zh
    low = raw.lower()
    if "inappropriate content" in low:
        return "内容安全审核未通过：请更换图片或视频后再试。"
    if "invalid image type" in low or "valid image" in low:
        return "图片格式无效：请使用 PNG 或 JPEG 等常见格式重新上传角色图。"
    if raw.startswith("[") and "]" in raw:
        c = raw[1 : raw.index("]")]
        tail = raw[raw.index("]") + 1 :].strip()
        for key, zh in _WAN_ERROR_ZH:
            if key == c or key in c:
                return zh
        return f"万相错误（{c}）：{tail}" if tail else f"万相错误（{c}）"
    return f"万相服务错误：{raw}"


class WanService:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def update_key(self, api_key: str):
        self._api_key = api_key

    async def upload_bytes(self, filename: str, data: bytes) -> str:
        """Upload file bytes to DashScope temporary OSS storage.
        Returns an oss:// URL usable in DashScope API calls (valid 48h)."""
        if not data:
            raise Exception("上传数据为空")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/uploads",
                params={"action": "getPolicy", "model": "wan2.2-animate-mix"},
                headers=headers,
            )
            if resp.status_code != 200:
                raise Exception(f"获取上传凭证失败 ({resp.status_code}): {resp.text[:300]}")
            cert = resp.json().get("data", {})

        upload_host = cert.get("upload_host", "")
        upload_dir = cert.get("upload_dir", "")
        if not upload_host or not upload_dir:
            raise Exception(f"上传凭证信息不完整: {cert}")

        key = f"{upload_dir}/{filename}"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        form_data = {
            "OSSAccessKeyId": cert["oss_access_key_id"],
            "Signature": cert["signature"],
            "policy": cert["policy"],
            "key": key,
            "x-oss-object-acl": cert.get("x_oss_object_acl", "private"),
            "x-oss-forbid-overwrite": cert.get("x_oss_forbid_overwrite", "true"),
            "success_action_status": "200",
            "x-oss-content-type": content_type,
        }

        logger.info("Uploading %s (%d bytes) to DashScope OSS...", filename, len(data))

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                upload_host,
                data=form_data,
                files={"file": (filename, data, content_type)},
            )
            if resp.status_code != 200:
                raise Exception(f"上传文件到 OSS 失败 ({resp.status_code}): {resp.text[:300]}")

        oss_url = f"oss://{key}"
        logger.info("File uploaded: %s -> %s", filename, oss_url)
        return oss_url

    async def replace_character(
        self,
        image_url: str,
        video_url: str,
        mode: str = "wan-std",
        check_image: bool = False,
    ) -> dict:
        """创建视频换人任务。
        image_url / video_url 支持 oss:// 或公网 HTTP URL。
        check_image: 万相官方参数；False 时跳过输入图片检测环节，可减少卡通/非真人脸误判。
        注意：输入/输出仍会走阿里云内容安全，视频侧误判无法通过此开关绕过。
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
            "X-DashScope-OssResourceResolve": "enable",
        }
        payload = {
            "model": "wan2.2-animate-mix",
            "input": {
                "image_url": image_url,
                "video_url": video_url,
            },
            "parameters": {
                "mode": mode,
                "check_image": check_image,
            },
        }

        logger.info("WAN replace_character: mode=%s, image=%s..., video=%s...",
                     mode, image_url[:80], video_url[:80])

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE_URL}/services/aigc/image2video/video-synthesis",
                headers=headers,
                json=payload,
            )
            if resp.status_code >= 400:
                body = resp.text[:800]
                logger.error("WAN API error %d: %s", resp.status_code, body)
                msg, code = body, ""
                try:
                    j = resp.json()
                    msg = j.get("message", j.get("msg", "")) or body[:300]
                    code = j.get("code", "") or ""
                except Exception:
                    pass
                raise Exception(localize_wan_error(msg, code))
            data = resp.json()

        output = data.get("output", {})
        task_id = output.get("task_id", "")
        if not task_id:
            raise Exception(f"万相未返回任务编号，请稍后重试。接口返回：{str(data)[:200]}")

        logger.info("WAN task created: %s", task_id)
        return {"task_id": task_id, "status": "processing", "provider": "wan"}

    async def query_task(self, task_id: str) -> dict:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/tasks/{task_id}",
                headers=headers,
            )
            if resp.status_code >= 400:
                return {"task_id": task_id, "status": "processing", "video_url": "",
                        "provider": "wan", "raw_status": "unknown"}
            data = resp.json()

        output = data.get("output", {})
        task_status = output.get("task_status", "UNKNOWN")

        video_url = ""
        error = ""
        if task_status == "SUCCEEDED":
            results = output.get("results")
            # 官方文档：results 为对象 {"video_url": "https://..."}；部分版本可能为列表
            if isinstance(results, dict):
                video_url = results.get("video_url", "") or results.get("url", "")
            elif isinstance(results, list) and results:
                first = results[0]
                if isinstance(first, dict):
                    video_url = first.get("video_url", "") or first.get("url", "")
            if not video_url:
                video_url = output.get("video_url", "") or data.get("video_url", "")
        elif task_status in ("FAILED", "CANCELED"):
            error = output.get("message", "") or data.get("message", "")
            code = output.get("code", "") or data.get("code", "")
            if code:
                error = localize_wan_error(error, code)
            else:
                error = localize_wan_error(error, "")
            logger.error("WAN task %s failed: %s", task_id, error or data)

        status_map = {
            "SUCCEEDED": "completed",
            "FAILED": "failed",
            "CANCELED": "failed",
            "PENDING": "processing",
            "RUNNING": "processing",
        }
        mapped = status_map.get(task_status, "processing")

        return {
            "task_id": task_id,
            "status": mapped,
            "video_url": video_url,
            "error": error,
            "provider": "wan",
            "raw_status": task_status,
        }

    async def wait_for_video(self, task_id: str, timeout: int = 600, interval: int = 10) -> dict:
        elapsed = 0
        while elapsed < timeout:
            result = await self.query_task(task_id)
            if result["status"] in ("completed", "failed"):
                return result
            await asyncio.sleep(interval)
            elapsed += interval
        return {"task_id": task_id, "status": "timeout", "video_url": "", "provider": "wan"}
