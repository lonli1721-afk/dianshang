#!/usr/bin/env python3
"""Server-side read-only health watcher.

This script is designed to run on the production host itself from deploy's
crontab. It writes small JSON/text reports with retention, but never modifies
application data, restarts services, deletes media, or calls paid providers.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


DEFAULT_APP_DIR = Path("/home/deploy/game-video-tool")
DEFAULT_DATA_DIR = Path("/home/deploy/game-video-data")
DEFAULT_BACKUP_DIR = Path("/home/deploy/game-video-backups")
DEFAULT_REPORT_DIR = DEFAULT_BACKUP_DIR / "health-watch"
DEFAULT_HEALTH_URL = "http://127.0.0.1:57991/health"
DEFAULT_PROVIDER_QUEUE_URL = "http://127.0.0.1:57991/ops/provider-queue"
DEFAULT_SERVICE_NAME = "game-video-tool.service"


def load_health_report_module():
    path = Path(__file__).with_name("health-report.py")
    spec = importlib.util.spec_from_file_location("health_report_for_watch", path)
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


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{num}B"


def run_command(command: list[str], timeout_seconds: float) -> dict:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "error": f"timeout after {timeout_seconds}s",
        }
    except OSError as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": "", "error": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def service_status(service_name: str, timeout_seconds: float) -> dict:
    active = run_command(["systemctl", "is-active", service_name], timeout_seconds)
    show = run_command(["systemctl", "show", service_name, "--property=MainPID,ActiveState,SubState,RestartUSec"], timeout_seconds)
    details: dict[str, str] = {}
    for line in (show.get("stdout") or "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            details[key] = value
    return {
        "service": service_name,
        "active": active.get("stdout") == "active",
        "is_active": active,
        "details": details,
    }


def journal_report(service_name: str, tail_lines: int, timeout_seconds: float, health_report) -> dict:
    result = run_command(["journalctl", "-u", service_name, "-n", str(tail_lines), "--no-pager"], timeout_seconds)
    error_counts = {name: 0 for name in health_report.ERROR_PATTERNS}
    samples: list[str] = []
    if result.get("stdout"):
        for line in result["stdout"].splitlines():
            matched = False
            for name, pattern in health_report.ERROR_PATTERNS.items():
                if pattern.search(line):
                    error_counts[name] += 1
                    matched = True
            if matched and len(samples) < 10:
                samples.append(line[-500:])
    return {
        "ok": result.get("ok", False),
        "tail_lines": tail_lines,
        "error_counts": error_counts,
        "samples": samples,
        "error": result.get("error") or result.get("stderr") or "",
    }


def build_health_args(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        app_dir=args.app_dir,
        data_dir=args.data_dir,
        backup_dir=args.backup_dir,
        json_report=None,
        health_url=args.health_url,
        health_timeout_seconds=args.health_timeout_seconds,
        provider_queue_url=args.provider_queue_url,
        provider_queue_timeout_seconds=args.provider_queue_timeout_seconds,
        service_name=args.service_name,
        since_hours=args.since_hours,
        log_tail_lines=args.log_tail_lines,
        top_users=args.top_users,
        top_memory_processes=args.top_memory_processes,
        cloud_dbs_keep_count=args.cloud_dbs_keep_count,
        disk_warn_percent=args.disk_warn_percent,
        disk_block_percent=args.disk_block_percent,
        disk_min_free_gb=args.disk_min_free_gb,
        memory_warn_mb=args.memory_warn_mb,
        memory_critical_mb=args.memory_critical_mb,
    )


def count_stale_processing(health_payload: dict) -> int:
    return sum(int(value) for value in (health_payload.get("tasks", {}).get("stale_processing_by_provider") or {}).values())


def provider_queue_pressure(provider_queue: dict) -> list[str]:
    if not provider_queue.get("ok"):
        return ["provider_queue_unavailable"]
    snapshot = (provider_queue.get("body") or {}).get("snapshot") or {}
    findings: list[str] = []
    for provider, row in (snapshot.get("providers") or {}).items():
        if row.get("saturated") or int(row.get("waiting") or 0) > 0 or int(row.get("total_timeouts") or 0) > 0:
            findings.append(f"provider:{provider}")
    for provider, row in (snapshot.get("status_queries") or {}).get("providers", {}).items():
        if row.get("saturated") or int(row.get("waiting") or 0) > 0 or int(row.get("total_timeouts") or 0) > 0:
            findings.append(f"status_query:{provider}")
    for name, row in (snapshot.get("key_pools") or {}).items():
        project = row.get("project") or {}
        if int(project.get("waiting") or 0) > 0 or int(project.get("total_queue_timeouts") or 0) > 0:
            findings.append(f"key_pool:{name}")
    return findings


def classify_watch(service: dict, health_payload: dict, journal: dict, args: argparse.Namespace) -> tuple[str, list[str]]:
    critical: list[str] = []
    warnings: list[str] = []

    if not service.get("active"):
        critical.append("service_not_active")
    if not health_payload.get("health", {}).get("ok"):
        critical.append("health_endpoint_failed")

    for row in health_payload.get("disk") or []:
        if not row.get("exists"):
            warnings.append(f"disk_path_missing:{row.get('path')}")
            continue
        used_percent = float(row.get("used_percent") or 0)
        free_bytes = int(row.get("free_bytes") or 0)
        if used_percent >= args.disk_block_percent or free_bytes < args.disk_min_free_gb * 1024**3:
            critical.append(f"disk_block:{row.get('path')}")
        elif used_percent >= args.disk_warn_percent:
            warnings.append(f"disk_warn:{row.get('path')}")

    tasks = health_payload.get("tasks") or {}
    if tasks.get("db_errors"):
        critical.append("task_audit_db_errors")
    stale_count = count_stale_processing(health_payload)
    if stale_count:
        warnings.append(f"stale_processing:{stale_count}")

    for name, count in (tasks.get("recent_error_categories") or {}).items():
        count = int(count)
        if count and name in {"rate_limited_429", "upstream_503", "upstream_504_timeout", "network_fetch"}:
            warnings.append(f"recent_task_error:{name}:{count}")

    queue_findings = provider_queue_pressure(health_payload.get("provider_queue") or {})
    warnings.extend(queue_findings)

    service_memory = (health_payload.get("memory") or {}).get("service") or {}
    memory_status = service_memory.get("status")
    if memory_status == "critical":
        critical.append("memory_critical")
    elif memory_status == "warning":
        warnings.append("memory_warning")
    elif memory_status == "unknown":
        warnings.append("memory_unknown")

    log_counts = health_payload.get("logs", {}).get("error_counts") or {}
    journal_counts = journal.get("error_counts") or {}
    for name in ("traceback", "http_503", "http_504", "failed_fetch"):
        total = int(log_counts.get(name) or 0) + int(journal_counts.get(name) or 0)
        if total:
            warnings.append(f"log_error:{name}:{total}")
    if int(log_counts.get("http_429") or 0) + int(journal_counts.get("http_429") or 0):
        warnings.append("log_error:http_429")

    if critical:
        return "critical", critical + warnings
    if warnings:
        return "warning", warnings
    return "ok", ["No immediate blocker found by server-side health watch."]


def build_watch_report(args: argparse.Namespace) -> dict:
    health_report = load_health_report_module()
    health_payload = health_report.build_report(build_health_args(args))
    service = service_status(args.service_name, args.command_timeout_seconds)
    journal = journal_report(args.service_name, args.journal_tail_lines, args.command_timeout_seconds, health_report)
    severity, findings = classify_watch(service, health_payload, journal, args)
    return {
        "action": "server_health_watch",
        "readonly": True,
        "writes_reports_only": True,
        "created_at": now_iso(),
        "severity": severity,
        "findings": findings,
        "service": service,
        "health_report": health_payload,
        "journal": journal,
        "summary": {
            "service_active": bool(service.get("active")),
            "health_ok": bool(health_payload.get("health", {}).get("ok")),
            "disk": [
                {
                    "path": row.get("path"),
                    "used_percent": row.get("used_percent"),
                    "free_bytes": row.get("free_bytes"),
                }
                for row in health_payload.get("disk", [])
                if row.get("exists")
            ],
            "stale_processing_count": count_stale_processing(health_payload),
            "db_errors_count": len(health_payload.get("tasks", {}).get("db_errors") or []),
            "provider_queue_pressure": provider_queue_pressure(health_payload.get("provider_queue") or {}),
            "log_error_counts": health_payload.get("logs", {}).get("error_counts") or {},
            "journal_error_counts": journal.get("error_counts") or {},
            "memory": health_payload.get("memory", {}).get("service") or {},
        },
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summary_text(payload: dict) -> str:
    summary = payload.get("summary") or {}
    disk_parts = []
    for row in summary.get("disk") or []:
        free = human_size(int(row.get("free_bytes") or 0))
        disk_parts.append(f"{row.get('path')}: {row.get('used_percent')}% used, {free} free")
    lines = [
        f"created_at: {payload.get('created_at')}",
        f"severity: {payload.get('severity')}",
        f"service_active: {summary.get('service_active')}",
        f"health_ok: {summary.get('health_ok')}",
        f"stale_processing_count: {summary.get('stale_processing_count')}",
        f"db_errors_count: {summary.get('db_errors_count')}",
        f"provider_queue_pressure: {summary.get('provider_queue_pressure')}",
        "disk: " + ("; ".join(disk_parts) if disk_parts else "unknown"),
        "findings:",
    ]
    lines.extend(f"- {item}" for item in payload.get("findings") or [])
    return "\n".join(lines) + "\n"


def cleanup_retention(report_dir: Path, retention_hours: float, keep_latest_count: int) -> list[str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    files = sorted(
        [
            path for path in report_dir.iterdir()
            if path.is_file() and path.name.startswith("health-watch-20") and path.suffix in {".json", ".txt"}
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


def write_reports(args: argparse.Namespace, payload: dict) -> dict:
    report_dir = args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp_slug()
    json_path = report_dir / f"health-watch-{stamp}.json"
    text_path = report_dir / f"health-watch-{stamp}.txt"
    latest_json = report_dir / "health-watch-latest.json"
    latest_text = report_dir / "health-watch-latest.txt"
    text = summary_text(payload)
    write_json(json_path, payload)
    text_path.write_text(text, encoding="utf-8")
    write_json(latest_json, payload)
    latest_text.write_text(text, encoding="utf-8")
    deleted = cleanup_retention(report_dir, args.retention_hours, args.keep_latest_count)
    return {
        "json_report": str(json_path),
        "text_report": str(text_path),
        "latest_json": str(latest_json),
        "latest_text": str(latest_text),
        "retention_deleted": deleted,
    }


def print_summary(payload: dict, outputs: dict | None = None) -> None:
    print(summary_text(payload), end="")
    if outputs:
        print(f"json_report: {outputs['json_report']}")
        print(f"latest_json: {outputs['latest_json']}")
        print(f"retention_deleted: {len(outputs.get('retention_deleted') or [])}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Server-side read-only health watcher")
    parser.add_argument("--app-dir", type=Path, default=DEFAULT_APP_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--provider-queue-url", default=DEFAULT_PROVIDER_QUEUE_URL)
    parser.add_argument("--health-timeout-seconds", type=float, default=3)
    parser.add_argument("--provider-queue-timeout-seconds", type=float, default=3)
    parser.add_argument("--command-timeout-seconds", type=float, default=5)
    parser.add_argument("--since-hours", type=int, default=24)
    parser.add_argument("--log-tail-lines", type=int, default=5000)
    parser.add_argument("--journal-tail-lines", type=int, default=200)
    parser.add_argument("--top-users", type=int, default=10)
    parser.add_argument("--top-memory-processes", type=int, default=8)
    parser.add_argument("--cloud-dbs-keep-count", type=int, default=200)
    parser.add_argument("--disk-warn-percent", type=int, default=70)
    parser.add_argument("--disk-block-percent", type=int, default=90)
    parser.add_argument("--disk-min-free-gb", type=float, default=5)
    parser.add_argument("--memory-warn-mb", type=int, default=1200)
    parser.add_argument("--memory-critical-mb", type=int, default=1600)
    parser.add_argument("--retention-hours", type=float, default=24 * 7)
    parser.add_argument("--keep-latest-count", type=int, default=200)
    parser.add_argument("--no-write", action="store_true", help="Build and print a report without writing report files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_watch_report(args)
    outputs = None if args.no_write else write_reports(args, payload)
    print_summary(payload, outputs)
    return 2 if payload.get("severity") == "critical" else 0


if __name__ == "__main__":
    raise SystemExit(main())
