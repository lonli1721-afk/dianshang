"""Shared task status rules for provider-backed generation tasks."""
from __future__ import annotations


SUCCESS_STATUSES = {"completed", "succeeded", "success"}
FAILED_STATUSES = {"failed", "fail", "error", "canceled", "cancelled"}
TERMINAL_NON_PROVIDER_STATUSES = {"expired"}

COMPLETED_VIDEO_MISSING_ERROR = "视频任务已完成，但上游未返回视频地址，请重新生成。"
PROVIDER_VIDEO_CACHE_ERROR_PREFIX = "视频任务已完成，但结果视频保存到本地失败"
PROVIDER_VIDEO_CACHE_ERROR_SUFFIX = "可先点击“重新拉取结果”。"


def is_success_task_status(status: str) -> bool:
    return (status or "").lower() in SUCCESS_STATUSES


def is_failed_task_status(status: str) -> bool:
    return (status or "").lower() in FAILED_STATUSES


def terminal_task_result_from_db(task_id: str, task: dict | None) -> dict | None:
    if not task:
        return None
    status = str(task.get("status") or "")
    normalized = status.lower()
    video_url = str(task.get("video_url") or "")

    if is_success_task_status(status) and video_url.startswith("/api/files/"):
        return {
            "task_id": task_id,
            "status": status,
            "video_url": video_url,
            "error": str(task.get("error") or ""),
            "provider": str(task.get("provider") or ""),
            "model": str(task.get("model") or ""),
        }

    if is_failed_task_status(status) or normalized in TERMINAL_NON_PROVIDER_STATUSES:
        return {
            "task_id": task_id,
            "status": status,
            "video_url": video_url,
            "error": str(task.get("error") or ""),
            "provider": str(task.get("provider") or ""),
            "model": str(task.get("model") or ""),
        }

    return None


def should_retry_failed_provider_video_cache(task: dict | None) -> bool:
    """Allow a narrow provider recheck for failed tasks caused by local result caching.

    Normal provider/parameter failures remain terminal. This only covers the case
    where the provider had already completed but our local copy of the result
    video failed, so a later status query may still expose a usable provider URL.
    """
    if not task:
        return False
    if not is_failed_task_status(str(task.get("status") or "")):
        return False
    if str(task.get("video_url") or ""):
        return False
    if not str(task.get("external_task_id") or ""):
        return False
    if not str(task.get("provider") or ""):
        return False
    error = str(task.get("error") or "")
    return (
        PROVIDER_VIDEO_CACHE_ERROR_PREFIX in error
        or COMPLETED_VIDEO_MISSING_ERROR in error
    )


def _exception_detail(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    text = str(detail).strip() if detail is not None else ""
    if not text:
        text = str(exc).strip()
    if not text:
        text = exc.__class__.__name__ or "未知错误"
    return text


def provider_video_cache_error(exc: Exception) -> str:
    detail = _exception_detail(exc)[:300].strip()
    if detail.startswith(PROVIDER_VIDEO_CACHE_ERROR_PREFIX):
        message = detail
        if message.rstrip().endswith(("：", ":")):
            message = f"{PROVIDER_VIDEO_CACHE_ERROR_PREFIX}：未知错误"
    else:
        message = f"{PROVIDER_VIDEO_CACHE_ERROR_PREFIX}：{detail or '未知错误'}"

    if PROVIDER_VIDEO_CACHE_ERROR_SUFFIX not in message:
        if not message.endswith("。"):
            message += "。"
        message += PROVIDER_VIDEO_CACHE_ERROR_SUFFIX
    return message
