#!/usr/bin/env python3
"""Read-only task failure report.

This report answers one operational question:
"What failed recently, and where should we look first?"

It reads SQLite databases in read-only mode and writes small JSON/TXT reports.
It never updates application data, never calls provider APIs, never repairs
tasks, and never restarts services.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_DATA_DIR = Path("/home/deploy/game-video-data")
DEFAULT_BACKUP_DIR = Path("/home/deploy/game-video-backups")
DEFAULT_REPORT_DIR = DEFAULT_BACKUP_DIR / "task-failure-report"
SENSITIVE_TOKEN_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|secret|token|access[_-]?key|ak|sk)[=:：\s]+([A-Za-z0-9_\-]{8,})"
)
LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")


def load_task_audit_module():
    path = Path(__file__).with_name("task-state-audit.py")
    spec = importlib.util.spec_from_file_location("task_state_audit_for_failure_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def now_iso() -> str:
    return now_local().replace(microsecond=0).isoformat()


def timestamp_slug() -> str:
    return now_local().strftime("%Y%m%d-%H%M%S")


def iso_cutoff(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redact_text(value: str | None, limit: int) -> str:
    text = " ".join(str(value or "").split())
    text = SENSITIVE_TOKEN_RE.sub(lambda match: f"{match.group(1)}=***", text)
    text = LONG_TOKEN_RE.sub("***", text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def user_id_from_db_path(data_dir: Path, db_path: Path) -> str:
    try:
        rel = db_path.relative_to(data_dir / "users")
        return rel.parts[0] if rel.parts else ""
    except ValueError:
        return "global"


def fetch_project_names(conn: sqlite3.Connection, project_ids: list[str], table_exists) -> dict[str, str]:
    ids = [pid for pid in sorted(set(project_ids)) if pid]
    if not ids or not table_exists(conn, "game_projects"):
        return {}
    names: dict[str, str] = {}
    for pid in ids:
        row = conn.execute("SELECT name FROM game_projects WHERE id=?", (pid,)).fetchone()
        if row:
            names[pid] = row["name"] or ""
    return names


def severity_for(failed_count: int, db_errors: list[dict], warning_count: int) -> str:
    if db_errors:
        return "critical"
    if failed_count >= warning_count > 0:
        return "warning"
    return "ok"


def build_failure_report(args: argparse.Namespace) -> dict:
    audit = load_task_audit_module()
    data_dir = args.data_dir
    cutoff = iso_cutoff(args.since_hours)
    users = audit.load_user_index(data_dir)
    db_paths = audit.list_user_db_paths(data_dir)

    failed_by_category: Counter[str] = Counter()
    failed_by_provider: Counter[str] = Counter()
    failed_by_model: Counter[str] = Counter()
    failed_by_user: Counter[str] = Counter()
    category_by_provider: dict[str, Counter[str]] = defaultdict(Counter)
    db_errors: list[dict] = []
    samples: list[dict] = []
    failed_count = 0

    for db_path in db_paths:
        user_id = user_id_from_db_path(data_dir, db_path)
        user = users.get(user_id, {})
        try:
            conn = audit.connect_readonly(db_path)
        except sqlite3.Error as exc:
            db_errors.append({"db": str(db_path), "error": str(exc)})
            continue
        try:
            if not audit.table_exists(conn, "game_tasks"):
                continue
            rows = conn.execute(
                """
                SELECT id, project_id, type, provider, model, status, error, external_task_id, created_at, updated_at
                FROM game_tasks
                WHERE status IN ('failed', 'error', 'timeout')
                  AND (created_at >= ? OR updated_at >= ?)
                ORDER BY updated_at DESC
                """,
                (cutoff, cutoff),
            ).fetchall()
            project_names = fetch_project_names(conn, [row["project_id"] for row in rows], audit.table_exists)
            for row in rows:
                item = dict(row)
                provider = item.get("provider") or "unknown"
                model = item.get("model") or "unknown"
                category = audit.classify_task_error(item.get("error") or "")
                failed_count += 1
                failed_by_category[category] += 1
                failed_by_provider[provider] += 1
                failed_by_model[model] += 1
                failed_by_user[user_id] += 1
                category_by_provider[provider][category] += 1
                if len(samples) < args.sample_limit:
                    samples.append({
                        "user_id": user_id,
                        "username": user.get("username", ""),
                        "display_name": user.get("display_name", ""),
                        "team": user.get("team", ""),
                        "task_id": item.get("id", ""),
                        "project_id": item.get("project_id", ""),
                        "project_name": project_names.get(item.get("project_id", ""), ""),
                        "type": item.get("type", ""),
                        "provider": provider,
                        "model": model,
                        "status": item.get("status", ""),
                        "error_category": category,
                        "error_preview": redact_text(item.get("error"), args.error_preview_chars),
                        "has_external_task_id": bool(item.get("external_task_id")),
                        "created_at": item.get("created_at", ""),
                        "updated_at": item.get("updated_at", ""),
                    })
        except sqlite3.Error as exc:
            db_errors.append({"db": str(db_path), "error": str(exc)})
        finally:
            conn.close()

    recommendations: list[str] = []
    if db_errors:
        recommendations.append("只读打开部分用户数据库失败，先排查 db_errors，不要继续执行修复。")
    if failed_count <= 0:
        recommendations.append("最近窗口内没有失败任务。")
    else:
        top_category = failed_by_category.most_common(1)[0][0]
        top_provider = failed_by_provider.most_common(1)[0][0]
        recommendations.append(f"最近窗口内有 {failed_count} 个失败任务，优先查看 {top_provider}/{top_category}。")
        if top_category in {"rate_limited_429", "upstream_503", "upstream_504_timeout"}:
            recommendations.append("疑似上游容量或限流问题；先看 provider queue/key pool，不要自动降级模型。")
        if top_category in {"provider_billing_or_permission", "auth_or_key_error"}:
            recommendations.append("疑似上游账号欠费、权限或 API key 问题；先检查对应平台账号状态和全局 key，不要让用户反复付费尝试。")
        if top_category in {"parameter_error", "provider_reference_duration", "provider_media_mix", "provider_media_invalid"}:
            recommendations.append("疑似参数或密钥配置问题；先复核模型能力表、前端限制和全局 API key。")
        if top_category.startswith("provider_video_") or top_category == "provider_result_unavailable":
            recommendations.append("疑似结果缓存或上游结果链接问题；先用只读 probe 确认，不要直接修改任务。")

    return {
        "action": "task_failure_report",
        "readonly": True,
        "mutates_database": False,
        "calls_provider_api": False,
        "repairs_tasks": False,
        "created_at": now_iso(),
        "data_dir": str(data_dir),
        "since_hours": args.since_hours,
        "cutoff": cutoff,
        "db_count": len(db_paths),
        "user_count": len(users),
        "severity": severity_for(failed_count, db_errors, args.warning_count),
        "failed_count": failed_count,
        "failed_by_category": dict(failed_by_category.most_common()),
        "failed_by_provider": dict(failed_by_provider.most_common()),
        "failed_by_model": dict(failed_by_model.most_common(20)),
        "failed_by_user": {
            user_id: {
                "count": count,
                "username": users.get(user_id, {}).get("username", ""),
                "display_name": users.get(user_id, {}).get("display_name", ""),
                "team": users.get(user_id, {}).get("team", ""),
            }
            for user_id, count in failed_by_user.most_common(20)
        },
        "category_by_provider": {
            provider: dict(counter.most_common())
            for provider, counter in sorted(category_by_provider.items())
        },
        "samples": samples,
        "db_errors": db_errors,
        "recommendations": recommendations,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summary_text(payload: dict) -> str:
    lines = [
        f"created_at: {payload.get('created_at')}",
        f"severity: {payload.get('severity')}",
        f"readonly: {payload.get('readonly')}",
        f"since_hours: {payload.get('since_hours')}",
        f"failed_count: {payload.get('failed_count')}",
        f"failed_by_category: {payload.get('failed_by_category')}",
        f"failed_by_provider: {payload.get('failed_by_provider')}",
        f"db_errors: {len(payload.get('db_errors') or [])}",
        "recommendations:",
    ]
    lines.extend(f"- {row}" for row in payload.get("recommendations") or [])
    return "\n".join(lines) + "\n"


def cleanup_report_retention(report_dir: Path, retention_hours: float, keep_latest_count: int) -> list[str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    files = sorted(
        [
            path for path in report_dir.iterdir()
            if path.is_file() and path.name.startswith("task-failure-report-20") and path.suffix in {".json", ".txt"}
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    keep: set[Path] = set(files[: max(0, keep_latest_count)])
    deleted: list[str] = []
    for path in files:
        if path in keep:
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if mtime >= cutoff:
            continue
        path.unlink()
        deleted.append(str(path))
    return deleted


def write_report_dir(report_dir: Path | None, payload: dict, retention_hours: float, keep_latest_count: int) -> dict | None:
    if not report_dir:
        return None
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp_slug()
    json_path = report_dir / f"task-failure-report-{stamp}.json"
    text_path = report_dir / f"task-failure-report-{stamp}.txt"
    latest_json = report_dir / "task-failure-report-latest.json"
    latest_text = report_dir / "task-failure-report-latest.txt"
    write_json(json_path, payload)
    text = summary_text(payload)
    text_path.write_text(text, encoding="utf-8")
    write_json(latest_json, payload)
    latest_text.write_text(text, encoding="utf-8")
    deleted = cleanup_report_retention(report_dir, retention_hours, keep_latest_count)
    return {
        "json_report": str(json_path),
        "text_report": str(text_path),
        "latest_json": str(latest_json),
        "latest_text": str(latest_text),
        "retention_deleted": deleted,
    }


def print_summary(payload: dict, outputs: dict | None) -> None:
    print(summary_text(payload), end="")
    if outputs:
        print(f"json_report: {outputs['json_report']}")
        print(f"latest_json: {outputs['latest_json']}")
        print(f"retention_deleted: {len(outputs.get('retention_deleted') or [])}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only report for recent failed generation tasks.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--since-hours", type=float, default=24)
    parser.add_argument("--warning-count", type=int, default=1)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--error-preview-chars", type=int, default=360)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--retention-hours", type=float, default=24 * 7)
    parser.add_argument("--keep-latest-count", type=int, default=200)
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_failure_report(args)
    if args.json_report:
        write_json(args.json_report, payload)
    outputs = write_report_dir(args.report_dir, payload, args.retention_hours, args.keep_latest_count)
    print_summary(payload, outputs)
    if payload["severity"] == "critical":
        return 2
    if payload["severity"] == "warning" and args.fail_on_warning:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
