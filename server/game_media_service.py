"""Media file helpers for the game workbench.

Routes keep the HTTP contract; this module owns local media reference parsing,
safe deletion, and upload persistence rules.
"""
from __future__ import annotations

import json
import logging
import uuid

import database as db
import deps


logger = logging.getLogger("game")


def collect_file_urls(value) -> set[str]:
    urls: set[str] = set()
    if isinstance(value, str):
        if "/api/files/" in value:
            urls.add(value)
    elif isinstance(value, dict):
        for v in value.values():
            urls.update(collect_file_urls(v))
    elif isinstance(value, list):
        for v in value:
            urls.update(collect_file_urls(v))
    return urls


def local_filename(url: str) -> str:
    local = ""
    if "/api/files/" in url:
        raw = url.split("/api/files/", 1)[1].split("?", 1)[0].split("#", 1)[0]
        if "/" in raw or "\\" in raw:
            return ""
        local = "/api/files/" + raw
    if not local:
        local = deps._extract_local_file_path(url)
    if not local:
        return ""
    filename = local.rsplit("/", 1)[-1].split("?", 1)[0].split("#", 1)[0]
    if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
        return ""
    return filename


def project_file_urls(project_id: str) -> set[str]:
    urls: set[str] = set()
    for value in db.get_project_file_reference_values(project_id):
        try:
            urls.update(collect_file_urls(json.loads(value)))
        except Exception:
            urls.update(collect_file_urls(value))
    return urls


def is_filename_used_elsewhere(filename: str, exclude_project_id: str = "") -> bool:
    return db.is_file_referenced_elsewhere(filename, exclude_project_id=exclude_project_id)


def is_filename_used_in_project_state(filename: str, project_id: str = "") -> bool:
    return db.is_file_referenced_in_project_state(filename, project_id=project_id)


def delete_local_files(urls: set[str], exclude_project_id: str = "") -> dict:
    files_dir = deps.get_files_dir().resolve()
    deleted: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []
    for url in urls:
        filename = local_filename(url)
        if not filename:
            skipped.append(url)
            continue
        if exclude_project_id and is_filename_used_in_project_state(filename, exclude_project_id):
            skipped.append(filename)
            continue
        if is_filename_used_elsewhere(filename, exclude_project_id=exclude_project_id):
            skipped.append(filename)
            continue
        target = (files_dir / filename).resolve()
        try:
            target.relative_to(files_dir)
        except ValueError:
            skipped.append(filename)
            continue
        if not target.exists():
            missing.append(filename)
            continue
        if not target.is_file():
            skipped.append(filename)
            continue
        target.unlink()
        deleted.append(filename)
    return {"deleted": deleted, "skipped": skipped, "missing": missing}


async def save_game_upload(file, *, duration_lookup) -> dict:
    source_name = file.filename or "upload.bin"
    ext = source_name.rsplit(".", 1)[-1].lower() if "." in source_name else "bin"
    fname = f"game_{uuid.uuid4().hex[:10]}.{ext}"
    fpath = deps.get_files_dir() / fname
    size = await deps.write_upload_to_path(file, fpath)
    deps.notify_media_file_saved(fpath)
    local_url = f"/api/files/{fname}"
    duration_seconds = None
    if ext in {"mp4", "mov", "webm", "m4v"} or (file.content_type or "").startswith("video/"):
        try:
            duration_seconds = await duration_lookup(local_url)
        except Exception as exc:
            logger.warning("Video duration lookup failed for %s: %s", local_url, exc)
    logger.info("Game upload: %s -> %s (%d bytes)", source_name, local_url, size)
    return {
        "url": local_url,
        "filename": fname,
        "size": size,
        "duration_seconds": duration_seconds,
    }


async def media_info(url: str, *, duration_lookup) -> dict:
    duration_seconds = await duration_lookup(url)
    return {"duration_seconds": duration_seconds}
