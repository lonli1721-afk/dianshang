"""HTTP-facing orchestration for game task status routes.

This module keeps batch polling and cache-retry response rules out of the large
game router while leaving provider calls injected by the router.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException

import database as db
from provider_queue import run_limited_map
from task_status_policy import (
    is_success_task_status,
    should_retry_failed_provider_video_cache,
    terminal_task_result_from_db,
)
from task_status_query import StatusQueryBusyError, status_query_busy_result


DbCall = Callable[..., Awaitable[Any]]
TaskStatusQuery = Callable[..., Awaitable[dict]]


async def retry_game_task_result_cache(
    task_id: str,
    *,
    db_call: DbCall,
    query_task_status: TaskStatusQuery,
) -> dict:
    """Retry caching a provider-completed result without creating a new task."""
    gt = await db_call(db.get_game_task_by_external_id, task_id)
    if not gt:
        gt = await db_call(db.get_game_task, task_id)
    if not gt:
        raise HTTPException(404, "Task not found")

    terminal_result = terminal_task_result_from_db(task_id, gt)
    if terminal_result and is_success_task_status(str(gt.get("status") or "")):
        return terminal_result
    if not should_retry_failed_provider_video_cache(gt):
        raise HTTPException(400, "这个任务不是结果保存失败类型，不能重新拉取结果。")

    try:
        return await query_task_status(task_id, force_failed_cache_retry=True)
    except StatusQueryBusyError as exc:
        busy_result = terminal_task_result_from_db(task_id, gt) or status_query_busy_result(task_id)
        if should_retry_failed_provider_video_cache(gt):
            base_error = str(gt.get("error") or "")
            busy_result.update({
                "status": "failed",
                "video_url": "",
                "error": f"{base_error}（{str(exc) or '状态查询排队中，请稍后重试'}）",
            })
        return busy_result


async def batch_query_game_task_statuses(
    task_ids_input: list[str] | None,
    *,
    query_task_status: TaskStatusQuery,
    concurrency: int,
    batch_limit: int,
) -> dict:
    """Query multiple task statuses while preserving route response shape."""
    task_ids: list[str] = []
    results: dict[str, dict] = {}
    seen: set[str] = set()
    for task_id in task_ids_input or []:
        if not task_id or task_id in seen:
            continue
        seen.add(task_id)
        if len(task_ids) >= batch_limit:
            results[task_id] = {
                "task_id": task_id,
                "status": "processing",
                "message": "本轮任务较多，稍后继续查询",
            }
            continue
        task_ids.append(task_id)

    if not task_ids:
        return {"tasks": results}

    queried = await run_limited_map(
        task_ids,
        concurrency,
        query_task_status,
    )
    for task_id, result in zip(task_ids, queried):
        if isinstance(result, Exception):
            if isinstance(result, StatusQueryBusyError):
                results[task_id] = status_query_busy_result(task_id)
                continue
            if isinstance(result, HTTPException):
                detail = result.detail
            else:
                detail = str(result)
            results[task_id] = {
                "task_id": task_id,
                "status": "failed",
                "error": str(detail)[:500],
            }
            continue
        results[task_id] = result

    return {"tasks": results}
