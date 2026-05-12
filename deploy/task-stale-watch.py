#!/usr/bin/env python3
"""Read-only stale task watch.

This script narrows task-state-audit down to one operational question:
"Are any generation tasks stuck longer than the configured threshold?"

It never writes application data, never restarts services, never calls provider
APIs, and never repairs tasks. It is intended for manual checks or cron-style
alerts before a human-approved repair step.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_DATA_DIR = Path("/home/deploy/game-video-data")
DEFAULT_BACKUP_DIR = Path("/home/deploy/game-video-backups")
DEFAULT_REPORT_DIR = DEFAULT_BACKUP_DIR / "task-stale-watch"
DEFAULT_STALE_SECONDS = 300


def load_task_state_audit_module():
    path = Path(__file__).with_name("task-state-audit.py")
    spec = importlib.util.spec_from_file_location("task_state_audit_for_watch", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_audit_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        data_dir=args.data_dir,
        backup_dir=None,
        json_report=None,
        stale_hours=args.stale_seconds / 3600,
        since_hours=args.since_hours,
        sample_limit=args.sample_limit,
        prompt_preview_chars=args.prompt_preview_chars,
    )


def severity_for(audit_payload: dict, critical_count: int) -> str:
    if audit_payload.get("db_errors"):
        return "critical"
    stale_count = int(audit_payload.get("stale_processing_count") or 0)
    if stale_count <= 0:
        return "ok"
    if critical_count > 0 and stale_count >= critical_count:
        return "critical"
    return "warning"


def compact_stale_sample(audit_payload: dict) -> list[dict]:
    rows: list[dict] = []
    for item in audit_payload.get("stale_processing_sample") or []:
        rows.append({
            "task_id": item.get("task_id", ""),
            "external_task_id": item.get("external_task_id", ""),
            "username": item.get("username", ""),
            "display_name": item.get("display_name", ""),
            "team": item.get("team", ""),
            "project_id": item.get("project_id", ""),
            "project_name": item.get("project_name", ""),
            "type": item.get("type", ""),
            "provider": item.get("provider", ""),
            "model": item.get("model", ""),
            "updated_at": item.get("updated_at", ""),
            "age_since_update": item.get("age_since_update", ""),
            "age_since_update_seconds": item.get("age_since_update_seconds"),
            "candidate_action": item.get("candidate_action", ""),
        })
    return rows


def build_watch_report(args: argparse.Namespace) -> dict:
    audit_module = load_task_state_audit_module()
    audit_payload = audit_module.audit_tasks(build_audit_args(args))
    stale_count = int(audit_payload.get("stale_processing_count") or 0)
    severity = severity_for(audit_payload, args.critical_count)

    recommendations: list[str] = []
    if audit_payload.get("db_errors"):
        recommendations.append("只读打开部分用户数据库失败，请先排查 db_errors，不要执行修复。")
    if stale_count:
        recommendations.append("发现超时 processing 任务：先用 task-state-probe.py 只读查询上游状态，再等待用户批准后才允许 repair。")
        recommendations.append("不要删除任务或媒体文件；费用、历史和项目状态必须保留。")
    else:
        recommendations.append("未发现超过阈值的 processing 任务。")

    return {
        "action": "task_stale_watch",
        "readonly": True,
        "mutates_database": False,
        "calls_provider_api": False,
        "repairs_tasks": False,
        "threshold_seconds": args.stale_seconds,
        "severity": severity,
        "data_dir": str(args.data_dir),
        "stale_processing_count": stale_count,
        "stale_processing_by_provider": audit_payload.get("stale_processing_by_provider", {}),
        "stale_processing_by_user": audit_payload.get("stale_processing_by_user", {}),
        "status_total": audit_payload.get("status_total", {}),
        "db_errors": audit_payload.get("db_errors", []),
        "stale_processing_sample": compact_stale_sample(audit_payload),
        "recommendations": recommendations,
    }


def write_json_report(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")


def summary_text(payload: dict) -> str:
    lines = [
        f"severity: {payload.get('severity')}",
        f"readonly: {payload.get('readonly')}",
        f"threshold_seconds: {payload.get('threshold_seconds')}",
        f"stale_processing_count: {payload.get('stale_processing_count')}",
        f"stale_processing_by_provider: {payload.get('stale_processing_by_provider')}",
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
            if path.is_file() and path.name.startswith("task-stale-watch-20") and path.suffix in {".json", ".txt"}
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
    json_path = report_dir / f"task-stale-watch-{stamp}.json"
    text_path = report_dir / f"task-stale-watch-{stamp}.txt"
    latest_json = report_dir / "task-stale-watch-latest.json"
    latest_text = report_dir / "task-stale-watch-latest.txt"
    write_json_report(json_path, payload)
    text = summary_text(payload)
    text_path.write_text(text, encoding="utf-8")
    write_json_report(latest_json, payload)
    latest_text.write_text(text, encoding="utf-8")
    deleted = cleanup_report_retention(report_dir, retention_hours, keep_latest_count)
    return {
        "json_report": str(json_path),
        "text_report": str(text_path),
        "latest_json": str(latest_json),
        "latest_text": str(latest_text),
        "retention_deleted": deleted,
    }


def print_summary(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"readonly: {payload['readonly']}")
    print(f"severity: {payload['severity']}")
    print(f"threshold_seconds: {payload['threshold_seconds']}")
    print(f"stale_processing_count: {payload['stale_processing_count']}")
    print(f"stale_processing_by_provider: {payload['stale_processing_by_provider']}")
    print(f"db_errors: {len(payload['db_errors'])}")
    for row in payload["recommendations"]:
        print(f"- {row}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only watch for stuck processing video tasks.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--stale-seconds", type=int, default=DEFAULT_STALE_SECONDS)
    parser.add_argument("--critical-count", type=int, default=10)
    parser.add_argument("--since-hours", type=float, default=24)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--prompt-preview-chars", type=int, default=120)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--retention-hours", type=float, default=72)
    parser.add_argument("--keep-latest-count", type=int, default=288)
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_watch_report(args)
    write_json_report(args.json_report, payload)
    outputs = write_report_dir(args.report_dir, payload, args.retention_hours, args.keep_latest_count)
    print_summary(payload)
    if outputs:
        print(f"json_report: {outputs['json_report']}")
        print(f"latest_json: {outputs['latest_json']}")
        print(f"retention_deleted: {len(outputs.get('retention_deleted') or [])}")
    if payload["severity"] == "critical":
        return 2
    if payload["severity"] == "warning" and args.fail_on_warning:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
