"""Service helpers for best-effort game task record persistence.

Provider task creation must not be reported as failed just because the local
SQLite task row could not be written. Keep this module small and dependency
injected so routers and task-status services can share the same behavior.
"""
from __future__ import annotations

import logging
import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import database as db


DbCall = Callable[..., Awaitable[Any]]
VideoTaskStore = MutableMapping[str, MutableMapping[str, Any]]


def reference_video_path(reference_video_url: str = "", advanced_reference_videos: list | None = None) -> str:
    """Return the task record field used for one or more reference videos."""
    return (
        json.dumps(advanced_reference_videos, ensure_ascii=False)
        if advanced_reference_videos
        else reference_video_url
    )


def build_generate_task_record_payload(
    *,
    project_id: str,
    prompt: str,
    model: str,
    provider: str,
    character_refs: list | None = None,
    scene_refs: list | None = None,
    reference_video_url: str = "",
    advanced_reference_videos: list | None = None,
) -> dict:
    """Build the database payload for a generated-video task record."""
    return {
        "project_id": project_id,
        "type_": "generate",
        "prompt": prompt,
        "model": model,
        "provider": provider,
        "character_refs": character_refs,
        "scene_refs": scene_refs,
        "ref_video_path": reference_video_path(reference_video_url, advanced_reference_videos),
    }


def build_replace_task_record_payload(
    *,
    project_id: str,
    prompt: str,
    model: str,
    provider: str,
    character_ref: str,
    ref_video_url: str,
) -> dict:
    """Build the database payload for a video replacement task record."""
    return {
        "project_id": project_id,
        "type_": "replace",
        "prompt": prompt,
        "model": model,
        "provider": provider,
        "character_refs": [character_ref],
        "scene_refs": [],
        "ref_video_path": ref_video_url,
    }


async def ensure_game_task_record(
    task_id: str,
    payload: dict,
    *,
    db_call: DbCall,
    video_tasks: VideoTaskStore,
    logger: logging.Logger | None = None,
) -> str:
    """Persist a local task record without turning provider success into failure.

    Returns an empty string on success. When persistence fails, the original
    payload is kept in the in-memory provider task metadata so a later status
    query can retry the database write.
    """
    if not payload.get("project_id"):
        return ""

    try:
        await db_call(db.create_game_task, **payload, external_task_id=task_id)
        meta = video_tasks.get(task_id)
        if meta is not None:
            meta.pop("task_record_payload", None)
        return ""
    except Exception as exc:  # noqa: BLE001 - task persistence is best-effort by design.
        if logger is not None:
            logger.exception("Failed to persist game task record for %s", task_id)
        meta = video_tasks.get(task_id)
        if meta is not None:
            meta["task_record_payload"] = payload
        return f"任务已创建并开始执行，但本地任务记录保存失败：{str(exc)[:200]}"
