#!/usr/bin/env python3
"""Read-only task state audit for stuck generation tasks.

This script is intentionally local-only and dependency-free. It reads SQLite
databases in read-only mode, writes an optional report, and never updates task,
project, billing, or user records.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_DATA_DIR = Path(os.environ.get("GAME_VIDEO_DATA_DIR", "/home/deploy/game-video-data"))
DEFAULT_BACKUP_DIR = Path(os.environ.get("GAME_VIDEO_BACKUP_DIR", "/home/deploy/game-video-backups"))

TASK_ERROR_PATTERNS = {
    "rate_limited_429": re.compile(r"\b429\b|Too Many Requests|RESOURCE_EXHAUSTED|rate limit|quota", re.I),
    "provider_billing_or_permission": re.compile(r"Arrearage|overdue-payment|good standing|Access denied|欠费|未开通|权限", re.I),
    "provider_reference_duration": re.compile(r"15\.2|reference video.*duration|video total duration|参考视频.*时长|时长过长", re.I),
    "provider_media_mix": re.compile(r"first/last frame.*reference media|首尾帧.*参考|首帧.*参考", re.I),
    "provider_media_invalid": re.compile(r"resource not found|invalid url|Unable to download|InvalidImage|InvalidVideo|参考图片无效|参考视频无效|无法下载", re.I),
    "provider_video_missing_url": re.compile(r"上游未返回视频地址|未返回视频地址", re.I),
    "provider_video_remote_http_403": re.compile(r"远程链接返回 HTTP 403|结果视频保存到本地失败：.*\bHTTP 403\b", re.I),
    "provider_video_remote_http_404": re.compile(r"远程链接返回 HTTP 404|结果视频保存到本地失败：.*\bHTTP 404\b", re.I),
    "provider_video_remote_http_5xx": re.compile(r"远程链接返回 HTTP 5\d\d|结果视频保存到本地失败：.*\bHTTP 5\d\d\b", re.I),
    "provider_video_empty_download": re.compile(r"远程文件下载为空|下载为空|响应为空", re.I),
    "provider_video_local_write_failed": re.compile(r"本地写入失败|写入失败|No space left|Permission denied", re.I),
    "provider_video_unknown_cache_error": re.compile(r"结果视频保存到本地失败：未知错误", re.I),
    "provider_result_unavailable": re.compile(r"结果视频链接已过期|结果视频保存到本地失败|未返回视频地址|无法访问|远程文件下载失败", re.I),
    "upstream_503": re.compile(r"\b503\b|UNAVAILABLE|high demand|服务繁忙", re.I),
    "upstream_504_timeout": re.compile(r"\b504\b|DEADLINE_EXCEEDED|timeout|timed out|超时", re.I),
    "network_fetch": re.compile(r"Failed to fetch|network|connection|ECONN|socket|请求失败", re.I),
    "provider_queue_busy": re.compile(r"ProviderBusyError|排队超过|当前请求较多|queue", re.I),
    "content_safety": re.compile(r"内容安全|安全审核|DataInspectionFailed|safety|sensitive content", re.I),
    "parameter_error": re.compile(r"InvalidParameter|BadRequest|400|OversizeImage|exceeds the limit|参数|尺寸|格式", re.I),
    "auth_or_key_error": re.compile(r"\b401\b|\b403\b|Unauthorized|Forbidden|API key|invalid key|permission", re.I),
    "empty_model_output": re.compile(r"没有返回提示词|empty response|empty output|空结果", re.I),
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().astimezone().replace(microsecond=0).isoformat()


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_cutoff(hours: float) -> str:
    return (now_utc() - timedelta(hours=hours)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def list_user_db_paths(data_dir: Path) -> list[Path]:
    paths = [data_dir / "game_video.db"]
    users_dir = data_dir / "users"
    if users_dir.exists():
        paths.extend(sorted(users_dir.glob("*/database.db")))
    return [path for path in paths if path.exists()]


def load_user_index(data_dir: Path) -> dict[str, dict]:
    auth_db = data_dir / "auth.db"
    if not auth_db.exists():
        return {}
    try:
        conn = connect_readonly(auth_db)
    except sqlite3.Error:
        return {}
    try:
        if not table_exists(conn, "users"):
            return {}
        rows = conn.execute(
            """
            SELECT id, username, display_name, role, is_active, team, last_login
            FROM users
            """
        ).fetchall()
        return {row["id"]: dict(row) for row in rows}
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def classify_task_error(error: str) -> str:
    text = error or ""
    if not text.strip():
        return "no_error_text"
    for name, pattern in TASK_ERROR_PATTERNS.items():
        if pattern.search(text):
            return name
    return "unknown"


def preview_text(value: str | None, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def user_id_from_db_path(data_dir: Path, db_path: Path) -> str:
    try:
        rel = db_path.relative_to(data_dir / "users")
        return rel.parts[0] if rel.parts else ""
    except ValueError:
        return "global"


def fetch_project_names(conn: sqlite3.Connection, project_ids: Iterable[str]) -> dict[str, str]:
    ids = [pid for pid in sorted(set(project_ids)) if pid]
    if not ids or not table_exists(conn, "game_projects"):
        return {}
    names: dict[str, str] = {}
    for pid in ids:
        row = conn.execute("SELECT name FROM game_projects WHERE id=?", (pid,)).fetchone()
        if row:
            names[pid] = row["name"] or ""
    return names


def candidate_action(row: dict, age_seconds: float | None) -> str:
    external_task_id = row.get("external_task_id") or ""
    provider = (row.get("provider") or "").lower()
    if not external_task_id:
        return "orphan_processing_without_external_task_id"
    if age_seconds is not None and age_seconds >= 24 * 3600:
        if provider in {"jimeng", "seedance", "ark"}:
            return "query_seedance_status_then_mark_terminal_if_missing"
        return "query_provider_status_then_mark_terminal_if_missing"
    return "wait_or_query_provider_status"


def audit_tasks(args: argparse.Namespace) -> dict:
    data_dir = args.data_dir
    stale_cutoff = iso_cutoff(args.stale_hours)
    recent_cutoff = iso_cutoff(args.since_hours)
    users = load_user_index(data_dir)
    db_paths = list_user_db_paths(data_dir)

    status_total: Counter[str] = Counter()
    stale_by_provider: Counter[str] = Counter()
    stale_by_model: Counter[str] = Counter()
    stale_by_user: Counter[str] = Counter()
    recent_failed_by_provider: Counter[str] = Counter()
    recent_error_categories: Counter[str] = Counter()
    stale_tasks: list[dict] = []
    db_errors: list[dict] = []
    total_stale_count = 0
    current_time = now_utc()

    for db_path in db_paths:
        user_id = user_id_from_db_path(data_dir, db_path)
        user = users.get(user_id, {})
        try:
            conn = connect_readonly(db_path)
        except sqlite3.Error as exc:
            db_errors.append({"db": str(db_path), "error": str(exc)})
            continue
        try:
            if not table_exists(conn, "game_tasks"):
                continue
            for row in conn.execute("SELECT status, COUNT(*) AS count FROM game_tasks GROUP BY status"):
                status_total[row["status"] or "unknown"] += int(row["count"])

            stale_count_rows = conn.execute(
                """
                SELECT provider, model, COUNT(*) AS count
                FROM game_tasks
                WHERE status='processing' AND updated_at < ?
                GROUP BY provider, model
                """,
                (stale_cutoff,),
            ).fetchall()
            for row in stale_count_rows:
                provider = row["provider"] or "unknown"
                model = row["model"] or "unknown"
                count = int(row["count"])
                total_stale_count += count
                stale_by_provider[provider] += count
                stale_by_model[model] += count
                stale_by_user[user_id] += count

            recent_failed_rows = conn.execute(
                """
                SELECT provider, error
                FROM game_tasks
                WHERE status IN ('failed', 'error', 'timeout')
                  AND (created_at >= ? OR updated_at >= ?)
                """,
                (recent_cutoff, recent_cutoff),
            ).fetchall()
            for row in recent_failed_rows:
                recent_failed_by_provider[row["provider"] or "unknown"] += 1
                recent_error_categories[classify_task_error(row["error"] or "")] += 1

            rows = conn.execute(
                """
                SELECT id, project_id, type, prompt, provider, model, status,
                       external_task_id, video_url, error, created_at, updated_at
                FROM game_tasks
                WHERE status='processing' AND updated_at < ?
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (stale_cutoff, args.sample_limit),
            ).fetchall()
            project_names = fetch_project_names(conn, [row["project_id"] for row in rows])
            for row in rows:
                item = dict(row)
                updated_at = parse_timestamp(item.get("updated_at"))
                created_at = parse_timestamp(item.get("created_at"))
                age_seconds = (current_time - updated_at).total_seconds() if updated_at else None
                created_age_seconds = (current_time - created_at).total_seconds() if created_at else None
                stale_tasks.append({
                    "db": str(db_path),
                    "user_id": user_id,
                    "username": user.get("username", ""),
                    "display_name": user.get("display_name", ""),
                    "team": user.get("team", ""),
                    "task_id": item.get("id", ""),
                    "project_id": item.get("project_id", ""),
                    "project_name": project_names.get(item.get("project_id", ""), ""),
                    "type": item.get("type", ""),
                    "provider": item.get("provider", ""),
                    "model": item.get("model", ""),
                    "external_task_id": item.get("external_task_id", ""),
                    "has_video_url": bool(item.get("video_url")),
                    "has_error": bool(item.get("error")),
                    "error_category": classify_task_error(item.get("error", "")),
                    "prompt_preview": preview_text(item.get("prompt"), args.prompt_preview_chars),
                    "created_at": item.get("created_at", ""),
                    "updated_at": item.get("updated_at", ""),
                    "age_since_update_seconds": int(age_seconds) if age_seconds is not None else None,
                    "age_since_update": human_duration(age_seconds),
                    "age_since_create": human_duration(created_age_seconds),
                    "candidate_action": candidate_action(item, age_seconds),
                })
        except sqlite3.Error as exc:
            db_errors.append({"db": str(db_path), "error": str(exc)})
        finally:
            conn.close()

    stale_tasks.sort(key=lambda row: row.get("updated_at") or "")
    recommendations = build_recommendations(total_stale_count, stale_by_provider, stale_tasks, db_errors)
    return {
        "action": "task_state_audit",
        "readonly": True,
        "dry_run": True,
        "created_at": now_iso(),
        "data_dir": str(data_dir),
        "stale_hours": args.stale_hours,
        "stale_cutoff": stale_cutoff,
        "since_hours": args.since_hours,
        "recent_cutoff": recent_cutoff,
        "db_count": len(db_paths),
        "user_count": len(users),
        "status_total": dict(status_total),
        "stale_processing_count": total_stale_count,
        "stale_processing_by_provider": dict(stale_by_provider),
        "stale_processing_by_model": dict(stale_by_model.most_common(20)),
        "stale_processing_by_user": {
            user_id: {
                "count": count,
                "username": users.get(user_id, {}).get("username", ""),
                "display_name": users.get(user_id, {}).get("display_name", ""),
                "team": users.get(user_id, {}).get("team", ""),
            }
            for user_id, count in stale_by_user.most_common()
        },
        "recent_failed_by_provider": dict(recent_failed_by_provider),
        "recent_error_categories": dict(recent_error_categories),
        "stale_processing_sample": stale_tasks[: args.sample_limit],
        "db_errors": db_errors,
        "recommendations": recommendations,
    }


def build_recommendations(
    total_stale_count: int,
    stale_by_provider: Counter[str],
    stale_tasks: list[dict],
    db_errors: list[dict],
) -> list[str]:
    rows: list[str] = []
    if db_errors:
        rows.append("Some SQLite databases could not be opened read-only; inspect db_errors before acting.")
    if total_stale_count <= 0:
        rows.append("No stale processing tasks found by this audit window.")
        return rows
    providers = ", ".join(f"{provider}:{count}" for provider, count in stale_by_provider.most_common())
    rows.append(f"Found stale processing tasks: {total_stale_count} ({providers}).")
    orphan_count = sum(1 for item in stale_tasks if item.get("candidate_action") == "orphan_processing_without_external_task_id")
    if orphan_count:
        rows.append(f"{orphan_count} sampled stale tasks have no external_task_id; these are likely local orphan states.")
    old_seedance = [
        item for item in stale_tasks
        if item.get("candidate_action") == "query_seedance_status_then_mark_terminal_if_missing"
    ]
    if old_seedance:
        rows.append("Seedance/Jimeng stale tasks should be checked against provider status before any terminal status fix.")
    rows.append("Do not delete stale tasks; billing and history must remain even if projects were deleted.")
    return rows


def write_json_report(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_summary(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"readonly: {payload['readonly']} dry_run: {payload['dry_run']}")
    print(f"db_count: {payload['db_count']} user_count: {payload['user_count']}")
    print(f"status_total: {payload['status_total']}")
    print(f"stale_processing_count: {payload['stale_processing_count']}")
    print(f"stale_processing_by_provider: {payload['stale_processing_by_provider']}")
    print(f"stale_processing_by_user: {payload['stale_processing_by_user']}")
    print(f"recent_error_categories: {payload['recent_error_categories']}")
    print(f"db_errors: {len(payload['db_errors'])}")
    print("recommendations:")
    for row in payload["recommendations"]:
        print(f"- {row}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only task state audit")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--stale-hours", type=float, default=2)
    parser.add_argument("--since-hours", type=float, default=24)
    parser.add_argument("--sample-limit", type=int, default=50)
    parser.add_argument("--prompt-preview-chars", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = audit_tasks(args)
    write_json_report(args.json_report, payload)
    print_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
