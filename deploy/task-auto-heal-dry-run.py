#!/usr/bin/env python3
"""Read-only auto-heal candidate report for stuck video tasks.

This script composes task-state-probe.py and only classifies evidence. It never
updates SQLite, downloads provider media, caches files, or changes billing
records. Any real task repair must remain a separate, reviewed step.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_DATA_DIR = Path("/home/deploy/game-video-data")
DEFAULT_BACKUP_DIR = Path("/home/deploy/game-video-backups")
DEFAULT_REPORT_DIR = DEFAULT_BACKUP_DIR / "task-auto-heal-dry-run"
AUTO_ACTION = "can_repair_to_completed_after_cache_policy_review"


def load_task_state_probe_module():
    path = Path(__file__).with_name("task-state-probe.py")
    spec = importlib.util.spec_from_file_location("task_state_probe_for_auto_heal", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")


def classify_probe_row(row: dict) -> tuple[str, str]:
    local_status = str(row.get("local_status") or "").lower()
    provider_status = str(row.get("provider_status") or "").lower()
    has_video_url = bool(row.get("has_provider_video_url"))
    recommended_action = row.get("recommended_action") or ""
    provider_error = row.get("provider_error") or ""
    external_task_id = row.get("external_task_id") or ""

    if not external_task_id:
        return "manual_review", "缺少 external_task_id，不能自动处理。"
    if provider_error:
        return "manual_review", "上游状态查询有错误，必须人工复核。"
    if local_status != "processing":
        return "manual_review", "本地任务不是 processing，本包只处理卡住的 processing 候选。"
    if provider_status == "completed" and has_video_url and recommended_action == AUTO_ACTION:
        return "auto_repair_candidate", "上游已完成且有视频地址，可作为后续人工批准修复候选。"
    if provider_status == "completed" and not has_video_url:
        return "manual_review", "上游完成但没有视频地址，不能自动修复为成功。"
    if provider_status in {"processing", "queued", "pending", ""}:
        return "not_ready", "上游仍未完成，继续观察或按超时策略处理。"
    if provider_status == "failed":
        return "manual_review", "上游已失败，只能人工确认后写入失败原因。"
    return "manual_review", "状态不在自动候选规则内。"


def compact_candidate(row: dict, category: str, reason: str) -> dict:
    return {
        "category": category,
        "reason": reason,
        "db": row.get("db", ""),
        "task_id": row.get("task_id", ""),
        "external_task_id": row.get("external_task_id", ""),
        "user_id": row.get("user_id", ""),
        "username": row.get("username", ""),
        "display_name": row.get("display_name", ""),
        "team": row.get("team", ""),
        "project_id": row.get("project_id", ""),
        "project_name": row.get("project_name", ""),
        "provider": row.get("provider", ""),
        "model": row.get("model", ""),
        "local_status": row.get("local_status", ""),
        "local_updated_at": row.get("local_updated_at", ""),
        "provider_status": row.get("provider_status", ""),
        "raw_status": row.get("raw_status", ""),
        "has_provider_video_url": bool(row.get("has_provider_video_url")),
        "provider_error": row.get("provider_error", ""),
        "recommended_action": row.get("recommended_action", ""),
    }


def build_recommendations(payload: dict) -> list[str]:
    rows: list[str] = []
    if payload.get("db_errors"):
        rows.append("发现数据库只读审计错误：先排查 db_errors，不允许进入修复。")
    if payload.get("auto_repair_candidate_count"):
        rows.append("发现可自愈候选：仍需人工批准后，才能进入独立 repair 执行包。")
        rows.append("本报告不下载视频、不写数据库、不改变费用记录。")
    elif payload.get("probe_count"):
        rows.append("本轮没有自动候选，按 not_ready/manual_review 原因继续观察或人工复核。")
    else:
        rows.append("没有可探测任务，或缺少 provider key，未产生自动候选。")
    rows.append("禁止把 dry-run 报告直接当作执行结果；真实修复必须单任务 allowlist、备份、再执行。")
    return rows


def build_probe_args(args: argparse.Namespace, probe_module) -> argparse.Namespace:
    return probe_module.build_parser().parse_args([
        "--data-dir", str(args.data_dir),
        "--backup-dir", str(args.backup_dir),
        "--stale-hours", str(args.stale_hours),
        "--since-hours", str(args.since_hours),
        "--sample-limit", str(args.sample_limit),
        "--prompt-preview-chars", str(args.prompt_preview_chars),
        "--limit", str(args.limit),
        "--concurrency", str(args.concurrency),
        *(["--include-failed"] if args.include_failed else []),
        *sum((["--task-id", task_id] for task_id in args.task_id), []),
    ])


async def build_auto_heal_report_async(args: argparse.Namespace) -> dict:
    probe_module = load_task_state_probe_module()
    probe_payload = await probe_module.run_probe(build_probe_args(args, probe_module))
    rows: list[dict] = []
    counts = {"auto_repair_candidate": 0, "not_ready": 0, "manual_review": 0}
    for probe_row in probe_payload.get("probes") or []:
        category, reason = classify_probe_row(probe_row)
        counts[category] = counts.get(category, 0) + 1
        rows.append(compact_candidate(probe_row, category, reason))

    auto_candidates = [row for row in rows if row.get("category") == "auto_repair_candidate"]
    db_errors = list((probe_payload.get("audit_summary") or {}).get("db_errors") or [])
    payload = {
        "action": "task_auto_heal_dry_run",
        "readonly": True,
        "dry_run": True,
        "mutates_database": False,
        "downloads_media": False,
        "caches_media": False,
        "repairs_tasks": False,
        "calls_provider_api": True,
        "requires_human_approval": True,
        "created_at": probe_payload.get("created_at") or timestamp_slug(),
        "data_dir": str(args.data_dir),
        "stale_hours": args.stale_hours,
        "probe_count": int(probe_payload.get("probe_count") or 0),
        "candidate_count": len(rows),
        "candidate_counts": counts,
        "auto_repair_candidate_count": len(auto_candidates),
        "auto_repair_limit": args.max_auto_candidates,
        "auto_repair_candidates": auto_candidates[: max(0, args.max_auto_candidates)],
        "all_candidates": rows,
        "db_errors": db_errors,
        "probe_summary": {
            "candidate_count": probe_payload.get("candidate_count"),
            "candidate_counts": probe_payload.get("candidate_counts", {}),
            "api_key_present_by_provider": probe_payload.get("api_key_present_by_provider", {}),
            "audit_summary": probe_payload.get("audit_summary", {}),
            "recommendations": probe_payload.get("recommendations", []),
        },
    }
    payload["recommendations"] = build_recommendations(payload)
    return payload


def build_auto_heal_report(args: argparse.Namespace) -> dict:
    return asyncio.run(build_auto_heal_report_async(args))


def write_json_report(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summary_text(payload: dict) -> str:
    lines = [
        f"readonly: {payload.get('readonly')}",
        f"dry_run: {payload.get('dry_run')}",
        f"calls_provider_api: {payload.get('calls_provider_api')}",
        f"probe_count: {payload.get('probe_count')}",
        f"auto_repair_candidate_count: {payload.get('auto_repair_candidate_count')}",
        f"candidate_counts: {payload.get('candidate_counts')}",
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
            if path.is_file() and path.name.startswith("task-auto-heal-dry-run-20") and path.suffix in {".json", ".txt"}
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
    json_path = report_dir / f"task-auto-heal-dry-run-{stamp}.json"
    text_path = report_dir / f"task-auto-heal-dry-run-{stamp}.txt"
    latest_json = report_dir / "task-auto-heal-dry-run-latest.json"
    latest_text = report_dir / "task-auto-heal-dry-run-latest.txt"
    write_json_report(json_path, payload)
    text_path.write_text(summary_text(payload), encoding="utf-8")
    write_json_report(latest_json, payload)
    latest_text.write_text(summary_text(payload), encoding="utf-8")
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
    print(f"readonly: {payload['readonly']} dry_run: {payload['dry_run']}")
    print(f"probe_count: {payload['probe_count']}")
    print(f"auto_repair_candidate_count: {payload['auto_repair_candidate_count']}")
    print(f"candidate_counts: {payload['candidate_counts']}")
    for row in payload["recommendations"]:
        print(f"- {row}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only dry-run report for task auto-heal candidates.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--stale-hours", type=float, default=2)
    parser.add_argument("--since-hours", type=float, default=24)
    parser.add_argument("--sample-limit", type=int, default=50)
    parser.add_argument("--prompt-preview-chars", type=int, default=120)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--task-id", action="append", default=[], help="Limit probe to a local task id or external task id")
    parser.add_argument("--include-failed", action="store_true", help="Include explicit recoverable failed tasks in probe evidence")
    parser.add_argument("--max-auto-candidates", type=int, default=5)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--retention-hours", type=float, default=72)
    parser.add_argument("--keep-latest-count", type=int, default=288)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_auto_heal_report(args)
    write_json_report(args.json_report, payload)
    outputs = write_report_dir(args.report_dir, payload, args.retention_hours, args.keep_latest_count)
    print_summary(payload)
    if outputs:
        print(f"json_report: {outputs['json_report']}")
        print(f"latest_json: {outputs['latest_json']}")
        print(f"retention_deleted: {len(outputs.get('retention_deleted') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
