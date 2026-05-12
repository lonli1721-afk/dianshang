#!/usr/bin/env python3
"""Controlled repair for provider-completed stale video tasks.

Default mode is dry-run. Execute mode backs up each affected user database,
downloads provider video results into that user's files directory, and updates
only the matching stale game_tasks rows. It never deletes tasks, projects,
files, or billing history.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


DEFAULT_DATA_DIR = Path(os.environ.get("GAME_VIDEO_DATA_DIR", "/home/deploy/game-video-data"))
DEFAULT_BACKUP_DIR = Path(os.environ.get("GAME_VIDEO_BACKUP_DIR", "/home/deploy/game-video-backups"))
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
SEEDANCE_PROVIDERS = {"jimeng", "seedance", "ark"}
WAN_PROVIDERS = {"wan"}
HAPPYHORSE_PROVIDERS = {"happyhorse"}
REPAIRABLE_PROVIDERS = SEEDANCE_PROVIDERS | WAN_PROVIDERS | HAPPYHORSE_PROVIDERS
VIDEO_PRICE_PER_SECOND_CNY = {
    "seedance-2.0": 1.0,
    "seedance-2.0-fast": 0.8,
    "seedance-1.5-pro": 0.3,
    "happyhorse-1.0-t2v": 0.9,
    "happyhorse-1.0-i2v": 0.9,
    "happyhorse-1.0-r2v": 0.9,
    "happyhorse-1.0-video-edit": 0.9,
    "viduq3-pro": 0.95,
    "viduq3-turbo": 0.45,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def write_json_report(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def connect_db(path: Path, *, readonly: bool) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    else:
        conn = sqlite3.connect(str(path), timeout=20)
        conn.execute("PRAGMA busy_timeout=20000")
        conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()}


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def user_db_path(data_dir: Path, user_id: str) -> Path:
    if user_id == "global":
        return data_dir / "game_video.db"
    return data_dir / "users" / user_id / "database.db"


def user_files_dir(data_dir: Path, user_id: str) -> Path:
    if user_id == "global":
        return data_dir / "files"
    return data_dir / "users" / user_id / "files"


def load_settings(data_dir: Path) -> dict:
    path = data_dir / "settings.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return {}


def first_non_empty(*values: str | None) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def load_seedance_api_key(data_dir: Path) -> str:
    settings = load_settings(data_dir)
    return first_non_empty(
        os.environ.get("GAME_ARK_API_KEY"),
        os.environ.get("ARK_API_KEY"),
        settings.get("game_ark_api_key"),
        settings.get("ark_api_key"),
        settings.get("jimeng_api_key"),
    )


def load_dashscope_api_key(data_dir: Path) -> str:
    settings = load_settings(data_dir)
    return first_non_empty(
        os.environ.get("GAME_DASHSCOPE_API_KEY"),
        os.environ.get("DASHSCOPE_API_KEY"),
        settings.get("game_dashscope_api_key"),
        settings.get("dashscope_api_key"),
    )


def provider_family(provider: str) -> str:
    value = (provider or "").lower()
    if value in SEEDANCE_PROVIDERS:
        return "seedance"
    if value in WAN_PROVIDERS or value in HAPPYHORSE_PROVIDERS:
        return "wan"
    return "unknown"


def load_provider_api_keys(data_dir: Path) -> dict[str, str]:
    return {
        "seedance": load_seedance_api_key(data_dir),
        "wan": load_dashscope_api_key(data_dir),
    }


def row_to_dict(row: sqlite3.Row | None) -> dict:
    return dict(row) if row else {}


def integrity_check(db_path: Path) -> str:
    conn = connect_db(db_path, readonly=True)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        if row is None:
            return "missing_integrity_result"
        return str(row[0])
    finally:
        conn.close()


def candidate_updated_at(item: dict) -> str:
    return str(item.get("local_updated_at") or item.get("updated_at") or "").strip()


def validate_probe_payload(probe_payload: dict) -> list[str]:
    errors: list[str] = []
    if probe_payload.get("action") != "task_state_probe":
        errors.append("probe_report_action_mismatch")
    if probe_payload.get("mutates_database") not in (False, None):
        errors.append("probe_report_is_not_readonly")
    if not isinstance(probe_payload.get("probes", []), list):
        errors.append("probe_report_missing_probes")
    return errors


def candidate_local_status(item: dict) -> str:
    return (item.get("local_status") or "processing").lower()


def select_repair_candidates(
    probe_payload: dict,
    task_ids: set[str] | None = None,
    limit: int = 50,
    *,
    allow_failed_local_status: bool = False,
) -> list[dict]:
    allowed_statuses = {"processing"}
    if allow_failed_local_status:
        allowed_statuses.add("failed")
    candidates: list[dict] = []
    for item in probe_payload.get("probes", []):
        if (item.get("provider") or "").lower() not in REPAIRABLE_PROVIDERS:
            continue
        if candidate_local_status(item) not in allowed_statuses:
            continue
        if (item.get("provider_status") or "").lower() != "completed":
            continue
        if not item.get("has_provider_video_url"):
            continue
        if not item.get("task_id") or not item.get("external_task_id") or not item.get("user_id"):
            continue
        if task_ids and item["task_id"] not in task_ids and item["external_task_id"] not in task_ids:
            continue
        candidates.append(item)
        if len(candidates) >= limit:
            break
    return candidates


def select_provider_failed_candidates(
    probe_payload: dict,
    task_ids: set[str] | None = None,
    limit: int = 50,
) -> list[dict]:
    candidates: list[dict] = []
    for item in probe_payload.get("probes", []):
        if (item.get("provider") or "").lower() not in REPAIRABLE_PROVIDERS:
            continue
        if candidate_local_status(item) != "processing":
            continue
        if (item.get("provider_status") or "").lower() != "failed":
            continue
        if item.get("has_provider_video_url"):
            continue
        if not item.get("task_id") or not item.get("external_task_id") or not item.get("user_id"):
            continue
        if task_ids and item["task_id"] not in task_ids and item["external_task_id"] not in task_ids:
            continue
        candidates.append(item)
        if len(candidates) >= limit:
            break
    return candidates


def validate_candidates(candidates: list[dict], args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    seen_task_ids: set[str] = set()
    seen_external_ids: set[str] = set()
    for item in candidates:
        task_id = str(item.get("task_id") or "")
        external_task_id = str(item.get("external_task_id") or "")
        if task_id in seen_task_ids:
            errors.append(f"duplicate_task_id:{task_id}")
        if external_task_id in seen_external_ids:
            errors.append(f"duplicate_external_task_id:{external_task_id}")
        seen_task_ids.add(task_id)
        seen_external_ids.add(external_task_id)
        if args.execute and not candidate_updated_at(item):
            errors.append(f"missing_local_updated_at:{task_id}")
    if args.expected_count is not None and len(candidates) != args.expected_count:
        errors.append(f"expected_count_mismatch:expected={args.expected_count}:actual={len(candidates)}")
    if args.execute and not args.task_id:
        errors.append("execute_requires_task_id_allowlist")
    if args.execute and args.expected_count is None:
        errors.append("execute_requires_expected_count")
    if args.terminalize_provider_failed and not args.task_id:
        errors.append("terminalize_failed_requires_task_id_allowlist")
    return errors


def provider_failed_error_message(provider_result: dict) -> str:
    raw = str(provider_result.get("error") or "").strip()
    if not raw:
        return "上游生成失败，未生成视频。"
    if "OutputVideoSensitiveContentDetected" in raw or "copyright" in raw.lower() or "PolicyViolation" in raw:
        return f"上游生成失败：内容安全/版权限制，未生成视频。{raw[:300]}"
    return f"上游生成失败，未生成视频。{raw[:300]}"


def query_seedance_task(api_key: str, task_id: str) -> dict:
    # Kept dependency-free so this repair utility can run under system Python.
    url = f"{ARK_BASE_URL}/contents/generations/tasks/{task_id}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
        return {"status": "probe_error", "video_url": "", "error": f"HTTP {exc.code}: {body[:500]}", "raw_status": ""}
    except Exception as exc:  # noqa: BLE001 - report probe failures.
        return {"status": "probe_error", "video_url": "", "error": str(exc)[:500], "raw_status": ""}

    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "probe_error", "video_url": "", "error": f"invalid json: {body[:300]}", "raw_status": ""}

    data = raw.get("data", raw) if isinstance(raw, dict) else {}
    inner = data.get("data", data) if isinstance(data, dict) else {}
    if not isinstance(inner, dict):
        inner = raw if isinstance(raw, dict) else {}
    status_raw = (
        inner.get("status")
        or (data.get("status") if isinstance(data, dict) else None)
        or (raw.get("status") if isinstance(raw, dict) else None)
        or "processing"
    )
    status = map_provider_status(status_raw)
    video_url = extract_provider_video_url(inner)
    error = ""
    if status == "failed":
        error = str(inner.get("error", "") or inner.get("message", "") or "")
        if not error and isinstance(inner.get("content"), dict):
            error = str(inner["content"].get("error", "") or inner["content"].get("message", ""))
    if status == "completed" and not video_url:
        status = "failed"
        error = error or "provider completed without video_url"
    return {"status": status, "video_url": video_url, "error": error, "raw_status": status_raw}


def query_wan_task(api_key: str, task_id: str) -> dict:
    # Kept dependency-free so this repair utility can run under system Python.
    url = f"{DASHSCOPE_BASE_URL}/tasks/{task_id}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
        return {"status": "probe_error", "video_url": "", "error": f"HTTP {exc.code}: {body[:500]}", "raw_status": ""}
    except Exception as exc:  # noqa: BLE001 - report probe failures.
        return {"status": "probe_error", "video_url": "", "error": str(exc)[:500], "raw_status": ""}

    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "probe_error", "video_url": "", "error": f"invalid json: {body[:300]}", "raw_status": ""}

    output = raw.get("output", {}) if isinstance(raw, dict) else {}
    if not isinstance(output, dict):
        output = {}
    status_raw = output.get("task_status") or raw.get("status") or "UNKNOWN"
    status = map_wan_status(status_raw)
    video_url = extract_dashscope_video_url(output, raw if isinstance(raw, dict) else {})
    error = ""
    if status == "failed":
        error = str(output.get("message", "") or raw.get("message", "") or output.get("code", "") or raw.get("code", ""))
    if status == "completed" and not video_url:
        status = "failed"
        error = error or "provider completed without video_url"
    return {"status": status, "video_url": video_url, "error": error, "raw_status": status_raw}


def query_provider_task(api_key: str, task_id: str, provider: str = "") -> dict:
    family = provider_family(provider)
    if family == "wan":
        return query_wan_task(api_key, task_id)
    return query_seedance_task(api_key, task_id)


def map_provider_status(status_raw) -> str:
    text = str(status_raw or "").strip().lower()
    if text in {"succeeded", "success", "completed"}:
        return "completed"
    if text in {"failed", "expired", "cancelled", "canceled"}:
        return "failed"
    return "processing"


def map_wan_status(status_raw) -> str:
    text = str(status_raw or "").strip().upper()
    if text == "SUCCEEDED":
        return "completed"
    if text in {"FAILED", "CANCELED", "CANCELLED"}:
        return "failed"
    return "processing"


def extract_provider_video_url(inner: dict) -> str:
    content = inner.get("content", {})
    if isinstance(content, dict):
        for key in ("video_url", "output_url", "result_url", "url"):
            value = content.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        for key in ("video", "file", "result"):
            value = content.get(key)
            if isinstance(value, dict):
                for nested_key in ("url", "video_url", "output_url"):
                    nested = value.get(nested_key)
                    if isinstance(nested, str) and nested.startswith("http"):
                        return nested
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            video_url = item.get("video_url")
            if isinstance(video_url, dict):
                url = video_url.get("url", "")
            else:
                url = video_url if isinstance(video_url, str) else ""
            if isinstance(url, str) and url.startswith("http"):
                return url
    for key in ("output_url", "result_url", "video_url"):
        value = inner.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return ""


def extract_dashscope_video_url(output: dict, raw: dict | None = None) -> str:
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


def backup_user_db(db_path: Path, backup_dir: Path, user_id: str, task_ids: list[str]) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{user_id}-database.db"
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    try:
        dest = sqlite3.connect(str(backup_path))
        try:
            source.backup(dest)
            dest.execute(
                "CREATE TABLE IF NOT EXISTS _repair_backup_metadata (created_at TEXT, user_id TEXT, task_ids_json TEXT)"
            )
            dest.execute(
                "INSERT INTO _repair_backup_metadata (created_at, user_id, task_ids_json) VALUES (?,?,?)",
                (now_iso(), user_id, json.dumps(task_ids, ensure_ascii=False)),
            )
            dest.commit()
        finally:
            dest.close()
    finally:
        source.close()
    return backup_path


def infer_video_ext(content_type: str, url: str) -> str:
    lowered = (content_type or "").lower()
    if "webm" in lowered:
        return ".webm"
    if "quicktime" in lowered or "mov" in lowered:
        return ".mov"
    clean_url = url.split("?", 1)[0]
    suffix = Path(clean_url).suffix.lower()
    if suffix in {".mp4", ".webm", ".mov", ".m4v"}:
        return suffix
    return ".mp4"


def download_video_to_user_files(url: str, files_dir: Path, task_id: str, max_bytes: int, timeout: int) -> dict:
    files_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "game-video-tool-task-repair/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_length = int(resp.headers.get("content-length") or 0)
        if content_length and content_length > max_bytes:
            raise RuntimeError(f"remote video is too large: {content_length} bytes > {max_bytes}")
        ext = infer_video_ext(resp.headers.get("content-type", ""), url)
        filename = f"repaired_{task_id}_{uuid.uuid4().hex[:10]}{ext}"
        target = files_dir / filename
        tmp = tempfile.NamedTemporaryFile(prefix=f".{filename}.", suffix=".tmp", dir=files_dir, delete=False)
        tmp_path = Path(tmp.name)
        size = 0
        try:
            with tmp:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise RuntimeError(f"remote video exceeded max bytes: {size} > {max_bytes}")
                    tmp.write(chunk)
            tmp_path.replace(target)
        except Exception:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise
    if size <= 0:
        try:
            target.unlink()
        except OSError:
            pass
        raise RuntimeError("downloaded video is empty")
    return {"filename": filename, "path": str(target), "size_bytes": size, "local_url": f"/api/files/{filename}"}


def check_provider_url_access(url: str, timeout: int) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "game-video-tool-task-repair/1.0"}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {
                "accessible": 200 <= int(resp.status) < 400,
                "status_code": int(resp.status),
                "content_length": resp.headers.get("content-length", ""),
                "error": "",
                "method": "HEAD",
            }
    except urllib.error.HTTPError as exc:
        head_error = {"status_code": int(exc.code), "error": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001 - report URL validation failures.
        head_error = {"status_code": 0, "error": str(exc)[:300]}

    # Some provider result URLs reject HEAD but allow GET. Use a one-byte range
    # request as the dry-run access proof without downloading the whole video.
    range_req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "game-video-tool-task-repair/1.0",
            "Range": "bytes=0-0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(range_req, timeout=timeout) as resp:
            return {
                "accessible": 200 <= int(resp.status) < 400,
                "status_code": int(resp.status),
                "content_length": resp.headers.get("content-length", ""),
                "error": "",
                "method": "GET_RANGE",
                "head_status_code": head_error["status_code"],
                "head_error": head_error["error"],
            }
    except urllib.error.HTTPError as exc:
        return {
            "accessible": False,
            "status_code": int(exc.code),
            "content_length": "",
            "error": f"HTTP {exc.code}",
            "method": "GET_RANGE",
            "head_status_code": head_error["status_code"],
            "head_error": head_error["error"],
        }
    except Exception as exc:  # noqa: BLE001 - report URL validation failures.
        return {
            "accessible": False,
            "status_code": 0,
            "content_length": "",
            "error": str(exc)[:300],
            "method": "GET_RANGE",
            "head_status_code": head_error["status_code"],
            "head_error": head_error["error"],
        }


def probe_video_duration_seconds(path: Path) -> float | None:
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        raw = (completed.stdout or "").strip()
        if raw:
            duration = float(raw)
            if duration > 0:
                return duration
    except Exception:
        pass
    return read_mp4_duration_seconds(path)


def read_mp4_duration_seconds(path: Path) -> float | None:
    def read_box_header(handle):
        header = handle.read(8)
        if len(header) < 8:
            return None
        size = int.from_bytes(header[:4], "big")
        box_type = header[4:8]
        header_size = 8
        if size == 1:
            extended = handle.read(8)
            if len(extended) < 8:
                return None
            size = int.from_bytes(extended, "big")
            header_size = 16
        elif size == 0:
            size = path.stat().st_size - handle.tell() + header_size
        if size < header_size:
            return None
        return size, box_type, header_size

    def scan_boxes(handle, end_pos: int) -> float | None:
        while handle.tell() + 8 <= end_pos:
            box_start = handle.tell()
            header = read_box_header(handle)
            if not header:
                return None
            size, box_type, _header_size = header
            box_end = min(box_start + size, end_pos)
            payload_size = box_end - handle.tell()
            if payload_size < 0:
                return None
            if box_type == b"mvhd":
                payload = handle.read(min(payload_size, 32))
                if len(payload) < 20:
                    return None
                version = payload[0]
                if version == 1:
                    if len(payload) < 32:
                        return None
                    timescale = int.from_bytes(payload[20:24], "big")
                    duration = int.from_bytes(payload[24:32], "big")
                else:
                    timescale = int.from_bytes(payload[12:16], "big")
                    duration = int.from_bytes(payload[16:20], "big")
                return duration / timescale if timescale > 0 and duration > 0 else None
            if box_type == b"moov":
                duration = scan_boxes(handle, box_end)
                if duration:
                    return duration
            handle.seek(box_end)
        return None

    try:
        with path.open("rb") as handle:
            return scan_boxes(handle, path.stat().st_size)
    except OSError:
        return None


def billing_patch(model: str, video_path: Path) -> dict:
    price = VIDEO_PRICE_PER_SECOND_CNY.get(model or "")
    if not price:
        return {"billing_status": "unpriced"}
    duration = probe_video_duration_seconds(video_path)
    if not duration:
        return {"billing_status": "duration_missing"}
    billable_seconds = round(duration, 2)
    return {
        "billable_video_seconds": billable_seconds,
        "estimated_cost_cny": round(billable_seconds * price, 2),
        "billing_status": "snapshot",
    }


def update_project_scenes(conn: sqlite3.Connection, project_id: str, task_ids: set[str], local_url: str) -> dict:
    row = conn.execute("SELECT scenes_json FROM game_projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        return {"project_found": False, "scene_updates": 0}
    try:
        data = json.loads(row["scenes_json"] or "{}")
    except Exception:
        return {"project_found": True, "scene_updates": 0, "scene_error": "invalid scenes_json"}
    if isinstance(data, list):
        data = {"generate": data, "replace": [], "tabState": None}
    if not isinstance(data, dict):
        return {"project_found": True, "scene_updates": 0, "scene_error": "unsupported scenes_json"}
    scene_updates = 0
    for group in ("generate", "replace"):
        items = data.get(group)
        if not isinstance(items, list):
            continue
        for scene in items:
            if not isinstance(scene, dict):
                continue
            if str(scene.get("taskId") or "") not in task_ids:
                continue
            if scene.get("videoUrl") and scene.get("status") == "completed":
                continue
            scene["status"] = "completed"
            scene["videoUrl"] = local_url
            scene["error"] = ""
            scene["startTime"] = None
            scene_updates += 1
    if scene_updates:
        conn.execute(
            "UPDATE game_projects SET scenes_json=?, updated_at=? WHERE id=?",
            (json.dumps(data, ensure_ascii=False), now_iso(), project_id),
        )
    return {"project_found": True, "scene_updates": scene_updates}


def mark_project_scenes_failed(conn: sqlite3.Connection, project_id: str, task_ids: set[str], error: str) -> dict:
    row = conn.execute("SELECT scenes_json FROM game_projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        return {"project_found": False, "scene_updates": 0}
    try:
        data = json.loads(row["scenes_json"] or "{}")
    except Exception:
        return {"project_found": True, "scene_updates": 0, "scene_error": "invalid scenes_json"}
    if isinstance(data, list):
        data = {"generate": data, "replace": [], "tabState": None}
    if not isinstance(data, dict):
        return {"project_found": True, "scene_updates": 0, "scene_error": "unsupported scenes_json"}
    scene_updates = 0
    for group in ("generate", "replace"):
        items = data.get(group)
        if not isinstance(items, list):
            continue
        for scene in items:
            if not isinstance(scene, dict):
                continue
            if str(scene.get("taskId") or "") not in task_ids:
                continue
            if scene.get("status") == "failed" and scene.get("error") == error:
                continue
            scene["status"] = "failed"
            scene["error"] = error
            scene["startTime"] = None
            scene_updates += 1
    if scene_updates:
        conn.execute(
            "UPDATE game_projects SET scenes_json=?, updated_at=? WHERE id=?",
            (json.dumps(data, ensure_ascii=False), now_iso(), project_id),
        )
    return {"project_found": True, "scene_updates": scene_updates}


def update_task_row(
    conn: sqlite3.Connection,
    task: dict,
    local_url: str,
    local_path: Path,
    *,
    repair_scenes: bool,
    expected_status: str = "processing",
) -> dict:
    row = conn.execute(
        """
        SELECT *
        FROM game_tasks
        WHERE id=? AND external_task_id=?
        """,
        (task["task_id"], task["external_task_id"]),
    ).fetchone()
    if not row:
        return {"updated": False, "reason": "task_not_found"}
    current = dict(row)
    if (current.get("status") or "").lower() != expected_status:
        return {"updated": False, "reason": f"task_status_changed:{current.get('status')}"}
    if (current.get("provider") or "").lower() not in REPAIRABLE_PROVIDERS:
        return {"updated": False, "reason": f"provider_mismatch:{current.get('provider')}"}
    expected_updated_at = candidate_updated_at(task)
    if expected_updated_at and current.get("updated_at") != expected_updated_at:
        return {
            "updated": False,
            "reason": "updated_at_changed",
            "expected_updated_at": expected_updated_at,
            "current_updated_at": current.get("updated_at", ""),
        }

    columns = table_columns(conn, "game_tasks")
    values = {
        "status": "completed",
        "video_url": local_url,
        "error": "",
        "updated_at": now_iso(),
    }
    values.update(billing_patch(current.get("model", ""), local_path))
    values = {key: value for key, value in values.items() if key in columns}
    assignments = ", ".join(f"{quote_ident(key)}=?" for key in values)
    params = list(values.values()) + [task["task_id"], task["external_task_id"], expected_status, current.get("updated_at", "")]
    cur = conn.execute(
        f"""
        UPDATE game_tasks
        SET {assignments}
        WHERE id=? AND external_task_id=? AND status=? AND updated_at=?
        """,
        params,
    )
    scene_result = {"project_found": False, "scene_updates": 0}
    if repair_scenes and current.get("project_id"):
        scene_result = update_project_scenes(
            conn,
            current.get("project_id", ""),
            {task["external_task_id"], task["task_id"]},
            local_url,
        )
    return {
        "updated": cur.rowcount == 1,
        "before_task": current,
        "task_patch": values,
        "scene_result": scene_result,
    }


def mark_task_failed(
    conn: sqlite3.Connection,
    task: dict,
    error_message: str,
    *,
    repair_scenes: bool,
    expected_status: str = "processing",
) -> dict:
    row = conn.execute(
        """
        SELECT *
        FROM game_tasks
        WHERE id=? AND external_task_id=?
        """,
        (task["task_id"], task["external_task_id"]),
    ).fetchone()
    if not row:
        return {"updated": False, "reason": "task_not_found"}
    current = dict(row)
    if (current.get("status") or "").lower() != expected_status:
        return {"updated": False, "reason": f"task_status_changed:{current.get('status')}"}
    if (current.get("provider") or "").lower() not in REPAIRABLE_PROVIDERS:
        return {"updated": False, "reason": f"provider_mismatch:{current.get('provider')}"}
    expected_updated_at = candidate_updated_at(task)
    if expected_updated_at and current.get("updated_at") != expected_updated_at:
        return {
            "updated": False,
            "reason": "updated_at_changed",
            "expected_updated_at": expected_updated_at,
            "current_updated_at": current.get("updated_at", ""),
        }

    columns = table_columns(conn, "game_tasks")
    values = {
        "status": "failed",
        "video_url": "",
        "error": error_message,
        "updated_at": now_iso(),
    }
    values = {key: value for key, value in values.items() if key in columns}
    assignments = ", ".join(f"{quote_ident(key)}=?" for key in values)
    params = list(values.values()) + [task["task_id"], task["external_task_id"], expected_status, current.get("updated_at", "")]
    cur = conn.execute(
        f"""
        UPDATE game_tasks
        SET {assignments}
        WHERE id=? AND external_task_id=? AND status=? AND updated_at=?
        """,
        params,
    )
    scene_result = {"project_found": False, "scene_updates": 0}
    if repair_scenes and current.get("project_id"):
        scene_result = mark_project_scenes_failed(
            conn,
            current.get("project_id", ""),
            {task["external_task_id"], task["task_id"]},
            error_message,
        )
    return {
        "updated": cur.rowcount == 1,
        "before_task": current,
        "task_patch": values,
        "scene_result": scene_result,
    }


def repair_tasks(
    args: argparse.Namespace,
    *,
    query_func: Callable[..., dict] = query_provider_task,
    download_func: Callable[[str, Path, str, int, int], dict] = download_video_to_user_files,
    access_check_func: Callable[[str, int], dict] = check_provider_url_access,
) -> dict:
    probe_payload = load_json(args.probe_report)
    task_ids = set(args.task_id or [])
    if args.terminalize_provider_failed:
        candidates = select_provider_failed_candidates(
            probe_payload,
            task_ids or None,
            args.limit,
        )
    else:
        candidates = select_repair_candidates(
            probe_payload,
            task_ids or None,
            args.limit,
            allow_failed_local_status=bool(args.allow_failed_local_status),
        )
    preflight_errors = validate_probe_payload(probe_payload)
    preflight_errors.extend(validate_candidates(candidates, args))
    api_keys = load_provider_api_keys(args.data_dir)
    execution_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_root = args.backup_dir / f"task-repair-before-{execution_id}"
    rows: list[dict] = []
    backups: dict[str, str] = {}
    integrity: dict[str, dict] = {}
    downloaded_files: list[str] = []
    should_abort = False

    for family in sorted({provider_family(item.get("provider", "")) for item in candidates}):
        if family == "unknown":
            preflight_errors.append("unsupported_provider_family")
        elif not api_keys.get(family):
            preflight_errors.append(f"missing_{family}_api_key")
    if preflight_errors:
        should_abort = True

    grouped_task_ids: dict[str, list[str]] = {}
    for item in candidates:
        grouped_task_ids.setdefault(item["user_id"], []).append(item["task_id"])

    if args.execute and not should_abort:
        for user_id, task_id_list in grouped_task_ids.items():
            db_path = user_db_path(args.data_dir, user_id)
            if not db_path.exists():
                should_abort = True
                rows.append({"user_id": user_id, "status": "skipped", "reason": f"db_not_found:{db_path}"})
                continue
            before_integrity = integrity_check(db_path)
            integrity[user_id] = {"before": before_integrity}
            if before_integrity != "ok":
                should_abort = True
                rows.append({
                    "user_id": user_id,
                    "status": "skipped",
                    "reason": f"db_integrity_failed_before:{before_integrity}",
                })
                continue
            backups[user_id] = str(backup_user_db(db_path, backup_root, user_id, task_id_list))

    for item in candidates:
        row = {
            "task_id": item.get("task_id", ""),
            "external_task_id": item.get("external_task_id", ""),
            "user_id": item.get("user_id", ""),
            "username": item.get("username", ""),
            "display_name": item.get("display_name", ""),
            "project_id": item.get("project_id", ""),
            "project_name": item.get("project_name", ""),
            "probe_local_updated_at": candidate_updated_at(item),
            "dry_run": not args.execute,
        }
        if should_abort:
            row.update({"status": "skipped", "reason": "preflight_failed", "preflight_errors": preflight_errors})
            rows.append(row)
            continue

        db_path = user_db_path(args.data_dir, item["user_id"])
        files_dir = user_files_dir(args.data_dir, item["user_id"])
        if not db_path.exists():
            row.update({"status": "skipped", "reason": f"db_not_found:{db_path}"})
            rows.append(row)
            continue

        family = provider_family(item.get("provider", ""))
        api_key = api_keys.get(family, "")
        try:
            provider_result = query_func(api_key, item["external_task_id"], item.get("provider", ""))
        except TypeError:
            provider_result = query_func(api_key, item["external_task_id"])
        row["provider_status"] = provider_result.get("status", "")
        row["provider_raw_status"] = provider_result.get("raw_status", "")
        row["provider_error"] = provider_result.get("error", "")
        provider_video_url = provider_result.get("video_url", "")
        row["has_provider_video_url"] = bool(provider_video_url)
        if args.terminalize_provider_failed:
            if provider_result.get("status") != "failed" or provider_video_url:
                row.update({"status": "skipped", "reason": "provider_not_failed_without_video"})
                rows.append(row)
                continue

            conn: sqlite3.Connection | None = None
            try:
                conn = connect_db(db_path, readonly=not args.execute)
                task_row = conn.execute(
                    "SELECT * FROM game_tasks WHERE id=?",
                    (item["task_id"],),
                ).fetchone()
                if not task_row:
                    row.update({"status": "skipped", "reason": "task_not_found"})
                    rows.append(row)
                    continue
                current = row_to_dict(task_row)
                row["before_task"] = current
                row["current_status"] = current.get("status", "")
                row["current_video_url"] = current.get("video_url", "")
                expected_status = candidate_local_status(item)
                if current.get("external_task_id") != item["external_task_id"]:
                    row.update({"status": "skipped", "reason": "external_task_id_mismatch"})
                    rows.append(row)
                    continue
                if (current.get("status") or "").lower() != expected_status:
                    row.update({"status": "skipped", "reason": f"task_status_changed:{current.get('status')}"})
                    rows.append(row)
                    continue
                expected_updated_at = candidate_updated_at(item)
                if expected_updated_at and current.get("updated_at") != expected_updated_at:
                    row.update({
                        "status": "skipped",
                        "reason": "updated_at_changed",
                        "expected_updated_at": expected_updated_at,
                        "current_updated_at": current.get("updated_at", ""),
                    })
                    rows.append(row)
                    continue

                error_message = provider_failed_error_message(provider_result)
                if not args.execute:
                    row.update({
                        "status": "would_mark_failed",
                        "reason": "provider_failed_without_video",
                        "error_message": error_message,
                        "would_update_task": True,
                        "would_repair_scenes": bool(args.repair_scenes),
                    })
                    rows.append(row)
                    continue

                conn.execute("BEGIN IMMEDIATE")
                update_result = mark_task_failed(
                    conn,
                    item,
                    error_message,
                    repair_scenes=bool(args.repair_scenes),
                    expected_status=expected_status,
                )
                if not update_result.get("updated"):
                    conn.rollback()
                    row.update({"status": "skipped", "reason": update_result.get("reason", "mark_failed_failed")})
                    rows.append(row)
                    continue
                conn.commit()
                after = conn.execute("SELECT * FROM game_tasks WHERE id=?", (item["task_id"],)).fetchone()
                row.update({
                    "status": "failed_marked",
                    "reason": "provider_failed_without_video",
                    "error_message": error_message,
                    "update_result": update_result,
                    "after_task": row_to_dict(after),
                })
                rows.append(row)
                continue
            except Exception as exc:  # noqa: BLE001 - report per-task failure and keep going.
                try:
                    if args.execute and conn:
                        conn.rollback()
                except Exception:
                    pass
                row.update({"status": "error", "reason": str(exc)[:500]})
                rows.append(row)
                continue
            finally:
                if conn:
                    conn.close()

        if provider_result.get("status") != "completed" or not provider_video_url:
            row.update({"status": "skipped", "reason": "provider_not_completed_with_video"})
            rows.append(row)
            continue

        conn: sqlite3.Connection | None = None
        download: dict | None = None
        try:
            conn = connect_db(db_path, readonly=not args.execute)
            task_row = conn.execute(
                "SELECT * FROM game_tasks WHERE id=?",
                (item["task_id"],),
            ).fetchone()
            if not task_row:
                row.update({"status": "skipped", "reason": "task_not_found"})
                rows.append(row)
                continue
            current = row_to_dict(task_row)
            row["before_task"] = current
            row["current_status"] = current.get("status", "")
            row["current_video_url"] = current.get("video_url", "")
            expected_status = candidate_local_status(item)
            if current.get("external_task_id") != item["external_task_id"]:
                row.update({"status": "skipped", "reason": "external_task_id_mismatch"})
                rows.append(row)
                continue
            if (current.get("status") or "").lower() != expected_status:
                row.update({"status": "skipped", "reason": f"task_status_changed:{current.get('status')}"})
                rows.append(row)
                continue
            expected_updated_at = candidate_updated_at(item)
            if expected_updated_at and current.get("updated_at") != expected_updated_at:
                row.update({
                    "status": "skipped",
                    "reason": "updated_at_changed",
                    "expected_updated_at": expected_updated_at,
                    "current_updated_at": current.get("updated_at", ""),
                })
                rows.append(row)
                continue
            if not args.execute:
                if args.validate_download_urls:
                    access = access_check_func(provider_video_url, min(args.download_timeout_seconds, 30))
                    row["provider_url_access"] = access
                    if not access.get("accessible"):
                        row.update({
                            "status": "would_mark_failed" if args.mark_failed_when_download_inaccessible else "skipped",
                            "reason": "provider_video_url_inaccessible",
                            "would_update_task": bool(args.mark_failed_when_download_inaccessible),
                            "would_repair_scenes": bool(args.repair_scenes),
                        })
                        rows.append(row)
                        continue
                row.update({
                    "status": "would_repair",
                    "would_download_to": str(files_dir),
                    "would_update_task": True,
                    "would_repair_scenes": bool(args.repair_scenes),
                })
                rows.append(row)
                continue

            try:
                download = download_func(
                    provider_video_url,
                    files_dir,
                    item["task_id"],
                    args.max_video_bytes,
                    args.download_timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001 - download failures can be terminalized explicitly.
                if not args.mark_failed_when_download_inaccessible:
                    raise
                error_message = args.inaccessible_failed_message
                conn.execute("BEGIN IMMEDIATE")
                update_result = mark_task_failed(
                    conn,
                    item,
                    error_message,
                    repair_scenes=bool(args.repair_scenes),
                    expected_status=expected_status,
                )
                if not update_result.get("updated"):
                    conn.rollback()
                    row.update({"status": "skipped", "reason": update_result.get("reason", "mark_failed_failed")})
                    rows.append(row)
                    continue
                conn.commit()
                after = conn.execute("SELECT * FROM game_tasks WHERE id=?", (item["task_id"],)).fetchone()
                row.update({
                    "status": "failed_marked",
                    "reason": "provider_video_url_inaccessible",
                    "download_error": str(exc)[:500],
                    "update_result": update_result,
                    "after_task": row_to_dict(after),
                })
                rows.append(row)
                continue
            local_url = download["local_url"]
            conn.execute("BEGIN IMMEDIATE")
            update_result = update_task_row(
                conn,
                item,
                local_url,
                Path(download["path"]),
                repair_scenes=bool(args.repair_scenes),
                expected_status=expected_status,
            )
            if not update_result.get("updated"):
                conn.rollback()
                try:
                    Path(download["path"]).unlink()
                    row["deleted_orphan_download"] = download["path"]
                except OSError:
                    row["orphan_download"] = download["path"]
                row.update({"status": "skipped", "reason": update_result.get("reason", "update_failed")})
                rows.append(row)
                continue
            conn.commit()
            downloaded_files.append(download["path"])
            after = conn.execute("SELECT * FROM game_tasks WHERE id=?", (item["task_id"],)).fetchone()
            row.update({
                "status": "repaired",
                "local_url": local_url,
                "download": download,
                "update_result": update_result,
                "after_task": row_to_dict(after),
            })
            rows.append(row)
        except Exception as exc:  # noqa: BLE001 - report per-task failure and keep going.
            try:
                if args.execute and conn:
                    conn.rollback()
            except Exception:
                pass
            try:
                if args.execute and download and download.get("path"):
                    Path(download["path"]).unlink()
                    row["deleted_orphan_download"] = download["path"]
            except Exception:
                row["orphan_download"] = download.get("path") if download else ""
            row.update({"status": "error", "reason": str(exc)[:500]})
            rows.append(row)
        finally:
            if conn:
                conn.close()

    if args.execute and backups:
        for user_id in backups:
            db_path = user_db_path(args.data_dir, user_id)
            if db_path.exists():
                integrity.setdefault(user_id, {})["after"] = integrity_check(db_path)

    repaired_count = sum(1 for item in rows if item.get("status") == "repaired")
    would_repair_count = sum(1 for item in rows if item.get("status") == "would_repair")
    would_mark_failed_count = sum(1 for item in rows if item.get("status") == "would_mark_failed")
    failed_marked_count = sum(1 for item in rows if item.get("status") == "failed_marked")
    skipped_count = sum(1 for item in rows if item.get("status") == "skipped")
    error_count = sum(1 for item in rows if item.get("status") == "error")
    integrity_error_count = sum(
        1
        for item in integrity.values()
        if item.get("before") not in ("", "ok", None) or item.get("after") not in ("", "ok", None)
    )
    return {
        "action": "task_state_repair",
        "created_at": now_iso(),
        "execute": bool(args.execute),
        "dry_run": not bool(args.execute),
        "data_dir": str(args.data_dir),
        "probe_report": str(args.probe_report),
        "preflight_errors": preflight_errors,
        "candidate_count": len(candidates),
        "repaired_count": repaired_count,
        "would_repair_count": would_repair_count,
        "would_mark_failed_count": would_mark_failed_count,
        "failed_marked_count": failed_marked_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "integrity_error_count": integrity_error_count,
        "backup_root": str(backup_root) if backups else "",
        "db_backups": backups,
        "db_integrity": integrity,
        "downloaded_files": downloaded_files,
        "rows": rows,
        "recommendations": build_recommendations(
            args.execute,
            repaired_count,
            would_repair_count,
            failed_marked_count,
            would_mark_failed_count,
            skipped_count,
            error_count,
            preflight_errors,
            integrity_error_count,
        ),
    }


def build_recommendations(
    execute: bool,
    repaired: int,
    would_repair: int,
    failed_marked: int,
    would_mark_failed: int,
    skipped: int,
    errors: int,
    preflight_errors: list[str],
    integrity_errors: int,
) -> list[str]:
    rows = []
    if preflight_errors:
        rows.append("Preflight failed: " + ", ".join(preflight_errors))
        return rows
    if integrity_errors:
        rows.append("SQLite integrity check failed; stop and inspect backups before further action.")
    if errors:
        rows.append("Errors occurred; inspect rows before further repair.")
    if not execute:
        rows.append(
            f"Dry-run only. {would_repair} tasks would be repaired; "
            f"{would_mark_failed} tasks would be marked failed; no files or databases were changed."
        )
        return rows
    rows.append(f"Execute completed. repaired={repaired}, failed_marked={failed_marked}, skipped={skipped}, errors={errors}.")
    rows.append("Run task-state-audit again to confirm stale processing count decreased.")
    return rows


def print_summary(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"execute: {payload['execute']} dry_run: {payload['dry_run']}")
    print(f"candidate_count: {payload['candidate_count']}")
    print(f"repaired_count: {payload['repaired_count']} would_repair_count: {payload['would_repair_count']}")
    print(f"failed_marked_count: {payload['failed_marked_count']} would_mark_failed_count: {payload['would_mark_failed_count']}")
    print(f"skipped_count: {payload['skipped_count']} error_count: {payload['error_count']}")
    print(f"preflight_errors: {payload['preflight_errors']}")
    print(f"integrity_error_count: {payload['integrity_error_count']}")
    print(f"backup_root: {payload['backup_root']}")
    print("recommendations:")
    for row in payload["recommendations"]:
        print(f"- {row}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controlled repair for provider-completed stale video tasks")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--probe-report", type=Path, required=True)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-count", type=int, default=None)
    parser.add_argument("--task-id", action="append", default=[], help="Limit repair to local task id or external task id")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-video-bytes", type=int, default=500 * 1024 * 1024)
    parser.add_argument("--download-timeout-seconds", type=int, default=120)
    parser.add_argument("--validate-download-urls", action="store_true")
    parser.add_argument("--mark-failed-when-download-inaccessible", action="store_true")
    parser.add_argument(
        "--terminalize-provider-failed",
        action="store_true",
        help="With explicit --task-id, mark a stale processing task failed when the provider still reports failed and no video URL.",
    )
    parser.add_argument(
        "--allow-failed-local-status",
        action="store_true",
        help="Allow explicitly selected failed local tasks to be repaired when provider has a completed video result.",
    )
    parser.add_argument(
        "--inaccessible-failed-message",
        default="上游任务已完成，但结果视频链接已过期或无法访问；请重新生成。",
    )
    parser.add_argument("--repair-scenes", action="store_true", help="Also patch matching processing scenes_json entries")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = repair_tasks(args)
    write_json_report(args.json_report, payload)
    print_summary(payload)
    return 1 if (
        payload.get("preflight_errors")
        or payload.get("error_count")
        or payload.get("integrity_error_count")
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
