from __future__ import annotations

import asyncio
import logging
import os
import uuid

from fastapi import HTTPException

import database as db
import deps

logger = logging.getLogger("viral")

MAX_VIRAL_UPLOAD_BYTES = max(
    1,
    int(os.environ.get("VIRAL_MAX_UPLOAD_BYTES", str(300 * 1024 * 1024)) or str(300 * 1024 * 1024)),
)


def safe_delete_local_file_if_unreferenced(file_url: str, user_id: str = "") -> dict:
    if not file_url:
        return {"deleted": [], "skipped": [], "missing": []}
    # Protect globally: viral files live in shared /api/files, so another user's
    # saved analysis or duplicate row must still keep the physical file alive.
    if db.is_viral_file_referenced(file_url):
        return {"deleted": [], "skipped": [file_url], "missing": []}

    local_path = deps.get_local_file_path_from_url(file_url)
    if not local_path:
        return {"deleted": [], "skipped": [], "missing": [file_url]}

    files_dir = deps.get_files_dir().resolve()
    target = local_path.resolve()
    try:
        target.relative_to(files_dir)
    except ValueError:
        return {"deleted": [], "skipped": [file_url], "missing": []}

    if not target.exists():
        return {"deleted": [], "skipped": [], "missing": [target.name]}
    if not target.is_file():
        return {"deleted": [], "skipped": [target.name], "missing": []}

    target.unlink()
    return {"deleted": [target.name], "skipped": [], "missing": []}


async def save_viral_upload(file, *, user_id: str) -> dict:
    source_name = file.filename or "viral-video.mp4"
    ext = source_name.rsplit(".", 1)[-1].lower() if "." in source_name else "mp4"
    if ext not in {"mp4", "mov", "webm", "m4v"}:
        raise HTTPException(400, "仅支持 mp4、mov、webm、m4v 视频文件。")

    filename = f"viral_{uuid.uuid4().hex[:10]}.{ext}"
    filepath = deps.get_files_dir() / filename
    try:
        size = await deps.write_upload_to_path(file, filepath)
        if size > MAX_VIRAL_UPLOAD_BYTES:
            filepath.unlink(missing_ok=True)
            raise HTTPException(413, f"单个视频不能超过 {MAX_VIRAL_UPLOAD_BYTES // 1024 // 1024}MB。")
        deps.notify_media_file_saved(filepath)
        file_url = f"/api/files/{filename}"
        duration_seconds = await asyncio.to_thread(deps.get_local_video_duration_seconds, file_url)
        record = await asyncio.to_thread(
            db.create_viral_video,
            user_id=user_id,
            source_name=source_name,
            file_url=file_url,
            file_size=size,
            duration_seconds=duration_seconds,
        )
    except HTTPException:
        raise
    except Exception:
        filepath.unlink(missing_ok=True)
        raise

    logger.info("Viral upload user=%s %s -> %s (%d bytes)", user_id, source_name, file_url, size)
    return record
