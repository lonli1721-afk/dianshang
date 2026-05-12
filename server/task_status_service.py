"""Service layer for provider-backed game task status queries.

The router owns HTTP shape; this module owns the task-state transition rules.
Keep provider calls, billing snapshots, and operation logging injected so this
module does not import large routers or provider services.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException

import database as db
import deps
from task_status_policy import (
    COMPLETED_VIDEO_MISSING_ERROR,
    is_failed_task_status,
    is_success_task_status,
    provider_video_cache_error,
    should_retry_failed_provider_video_cache,
    terminal_task_result_from_db,
)
from task_status_query import run_status_query


DbCall = Callable[..., Awaitable[Any]]
EnsureTaskRecord = Callable[[str, dict], Awaitable[str]]
ProviderStatusQuery = Callable[[str, str], Awaitable[dict]]
SnapshotBilling = Callable[[dict, dict], Awaitable[None]]
RecordOperationFailure = Callable[..., Awaitable[None]]


async def query_game_task_status(
    task_id: str,
    *,
    db_call: DbCall,
    query_provider_task_status: ProviderStatusQuery,
    ensure_game_task_record: EnsureTaskRecord,
    snapshot_completed_task_billing: SnapshotBilling,
    record_operation_failure: RecordOperationFailure,
    failed_result_recovery_retry_seconds: int,
    force_failed_cache_retry: bool = False,
) -> dict:
    """Query and persist one task status without exposing HTTP route concerns."""
    gt = await db_call(db.get_game_task_by_external_id, task_id)
    provider_task_id = task_id
    if not gt:
        gt = await db_call(db.get_game_task, task_id)
        if gt and gt.get("external_task_id"):
            provider_task_id = str(gt.get("external_task_id") or task_id)

    meta = deps._video_tasks.get(provider_task_id) or deps._video_tasks.get(task_id, {})
    terminal_result = terminal_task_result_from_db(task_id, gt)
    if terminal_result:
        if should_retry_failed_provider_video_cache(gt):
            meta = deps._video_tasks.setdefault(provider_task_id, meta or {})
            now = time.monotonic()
            last_attempt = float(meta.get("failed_result_recovery_attempt_at") or 0)
            if not force_failed_cache_retry and now - last_attempt < failed_result_recovery_retry_seconds:
                return terminal_result
            meta["failed_result_recovery_attempt_at"] = now
            if force_failed_cache_retry:
                meta["failed_result_recovery_forced_at"] = now
            meta["provider"] = meta.get("provider") or str(gt.get("provider") or "")
        else:
            return terminal_result

    provider = meta.get("provider", "") or (gt.get("provider", "") if gt else "")
    if provider and provider_task_id not in deps._video_tasks:
        deps._video_tasks[provider_task_id] = {"provider": provider}
    if not provider:
        raise HTTPException(404, "Task not found or provider is not configured")

    result = await run_status_query(
        provider,
        provider_task_id,
        lambda: query_provider_task_status(provider_task_id, provider),
    )
    result["task_id"] = task_id

    status = result.get("status", "")
    recovering_failed_cache = bool(gt and should_retry_failed_provider_video_cache(gt))
    if recovering_failed_cache and not is_success_task_status(status):
        deps._video_tasks.setdefault(provider_task_id, {})["failed_result_recovery_last_status"] = status
        return terminal_result or {
            "task_id": task_id,
            "status": gt.get("status", "failed") if gt else "failed",
            "video_url": gt.get("video_url", "") if gt else "",
            "error": gt.get("error", "") if gt else "",
            "provider": provider,
            "model": gt.get("model", "") if gt else "",
        }

    if is_success_task_status(status):
        existing_video_url = (gt or {}).get("video_url", "") or meta.get("video_url", "")
        if existing_video_url.startswith("/api/files/"):
            result["video_url"] = existing_video_url
        else:
            remote_video_url = result.get("video_url", "") or ""
            if not remote_video_url:
                result.update({
                    "status": "failed",
                    "video_url": "",
                    "error": COMPLETED_VIDEO_MISSING_ERROR,
                })
                status = result["status"]
            elif not remote_video_url.startswith("/api/files/"):
                try:
                    result["video_url"] = await deps.cache_remote_file(
                        remote_video_url,
                        ".mp4",
                        strict=True,
                        strict_error_message="视频任务已完成，但结果视频保存到本地失败",
                    )
                    deps._video_tasks.setdefault(provider_task_id, {})["video_url"] = result["video_url"]
                except Exception as exc:  # noqa: BLE001 - completed tasks must be terminalized if caching fails.
                    error_text = provider_video_cache_error(exc)
                    result.update({
                        "status": "failed",
                        "video_url": "",
                        "error": error_text,
                    })
                    status = result["status"]

    if not gt and meta.get("task_record_payload"):
        await ensure_game_task_record(task_id, meta["task_record_payload"])
        gt = await db_call(db.get_game_task_by_external_id, task_id)

    if gt:
        error_text = result.get("error") or result.get("message") or result.get("fail_reason") or ""
        await db_call(
            db.update_game_task,
            gt["id"],
            status=result.get("status", "processing"),
            video_url=result.get("video_url", ""),
            error=error_text if is_failed_task_status(status) else "",
        )
        if is_success_task_status(status) and gt.get("billing_status") != "snapshot":
            await snapshot_completed_task_billing(gt, result)
        if is_failed_task_status(status) and not recovering_failed_cache:
            operation = "replace_video" if gt.get("type") == "replace" else "generate_video"
            await record_operation_failure(
                operation,
                project_id=gt.get("project_id", ""),
                provider=provider,
                model=gt.get("model", ""),
                task_id=task_id,
                error=error_text or f"任务状态为 {status}",
            )

    return result
