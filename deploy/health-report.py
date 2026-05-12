#!/usr/bin/env python3
"""Read-only production health report.

The report is intentionally dependency-free and safe to run from cron. It does
not mutate application data or call external model providers.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_APP_DIR = Path(os.environ.get("GAME_VIDEO_APP_DIR", "/home/deploy/game-video-tool"))
DEFAULT_DATA_DIR = Path(os.environ.get("GAME_VIDEO_DATA_DIR", "/home/deploy/game-video-data"))
DEFAULT_BACKUP_DIR = Path(os.environ.get("GAME_VIDEO_BACKUP_DIR", "/home/deploy/game-video-backups"))
DEFAULT_HEALTH_URL = os.environ.get("GAME_VIDEO_HEALTH_URL", "http://127.0.0.1:57991/health")
DEFAULT_PROVIDER_QUEUE_URL = os.environ.get("GAME_VIDEO_PROVIDER_QUEUE_URL", "http://127.0.0.1:57991/ops/provider-queue")
DEFAULT_SERVICE_NAME = os.environ.get("GAME_VIDEO_SERVICE_NAME", "game-video-tool.service")

ERROR_PATTERNS = {
    "http_429": re.compile(r"\b429\b|Too Many Requests|RESOURCE_EXHAUSTED", re.I),
    "http_503": re.compile(r"\b503\b|UNAVAILABLE", re.I),
    "http_504": re.compile(r"\b504\b|DEADLINE_EXCEEDED|timeout", re.I),
    "failed_fetch": re.compile(r"Failed to fetch", re.I),
    "traceback": re.compile(r"Traceback|Exception|(^|\s)(ERROR|CRITICAL)[:\s-]", re.I),
}

FRONTEND_ASSET_PATTERN = re.compile(r"/assets/index-[A-Za-z0-9_-]+\.js")
VIRAL_OBS_PATTERN = re.compile(r"\bVIRAL_OBS\s+(?P<fields>.*)$")

PROVIDER_PATTERNS = {
    "gemini": re.compile(r"gemini|google", re.I),
    "seedance": re.compile(r"seedance|jimeng|volcengine|doubao", re.I),
    "happyhorse": re.compile(r"happyhorse|dashscope|happy horse", re.I),
    "vidu": re.compile(r"\bvidu\b", re.I),
    "wan": re.compile(r"\bwan\b|通义万相", re.I),
}

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


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def since_iso(hours: int) -> str:
    value = datetime.now(timezone.utc) - timedelta(hours=hours)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{num}B"


def parse_kb_status_value(value: str) -> int:
    match = re.match(r"^\s*(\d+)\s*kB\s*$", value)
    if not match:
        return 0
    return int(match.group(1)) * 1024


def read_proc_status(pid: int, proc_root: Path = Path("/proc")) -> dict:
    status_path = proc_root / str(pid) / "status"
    if not status_path.exists():
        return {}
    row: dict[str, int | str] = {}
    try:
        for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            value = value.strip()
            if key in {"VmRSS", "VmHWM", "VmSize", "VmData", "VmStk", "VmExe", "VmSwap"}:
                row[f"{key.lower()}_bytes"] = parse_kb_status_value(value)
            elif key == "Threads":
                try:
                    row["threads"] = int(value)
                except ValueError:
                    row["threads"] = 0
            elif key in {"Name", "State"}:
                row[key.lower()] = value
    except OSError:
        return {}
    return row


def read_proc_cmdline(pid: int, proc_root: Path = Path("/proc")) -> str:
    cmdline_path = proc_root / str(pid) / "cmdline"
    try:
        raw = cmdline_path.read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()


def count_proc_fds(pid: int, proc_root: Path = Path("/proc")) -> int | None:
    fd_dir = proc_root / str(pid) / "fd"
    try:
        return len(list(fd_dir.iterdir()))
    except OSError:
        return None


def read_meminfo(proc_root: Path = Path("/proc")) -> dict:
    meminfo_path = proc_root / "meminfo"
    if not meminfo_path.exists():
        return {"available": False}
    values: dict[str, int] = {}
    try:
        for line in meminfo_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                values[f"{key.lower()}_bytes"] = parse_kb_status_value(value)
    except OSError as exc:
        return {"available": False, "error": str(exc)}
    total = int(values.get("memtotal_bytes") or 0)
    available = int(values.get("memavailable_bytes") or 0)
    used_percent = round((total - available) / total * 100, 2) if total else 0
    return {"available": True, **values, "memory_used_percent": used_percent}


def find_service_pid(service_name: str, timeout_seconds: float = 2) -> dict:
    try:
        completed = subprocess.run(
            ["systemctl", "show", service_name, "--property=MainPID", "--value"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"pid": 0, "method": "systemctl", "error": str(exc)}
    text = (completed.stdout or "").strip()
    if completed.returncode != 0:
        return {"pid": 0, "method": "systemctl", "error": (completed.stderr or "").strip()}
    try:
        pid = int(text)
    except ValueError:
        pid = 0
    return {"pid": pid, "method": "systemctl", "error": "" if pid else f"invalid MainPID: {text!r}"}


def scan_process_memory(proc_root: Path = Path("/proc"), top_count: int = 8) -> list[dict]:
    if not proc_root.exists():
        return []
    rows: list[dict] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        status = read_proc_status(pid, proc_root)
        if not status:
            continue
        rows.append({
            "pid": pid,
            "name": status.get("name") or "",
            "state": status.get("state") or "",
            "rss_bytes": int(status.get("vmrss_bytes") or 0),
            "peak_rss_bytes": int(status.get("vmhwm_bytes") or 0),
            "threads": int(status.get("threads") or 0),
            "cmdline": read_proc_cmdline(pid, proc_root)[:300],
        })
    rows.sort(key=lambda row: row["rss_bytes"], reverse=True)
    return rows[:top_count]


def memory_report(
    service_name: str,
    warn_mb: int,
    critical_mb: int,
    top_processes: int,
    proc_root: Path = Path("/proc"),
) -> dict:
    system = read_meminfo(proc_root)
    service_lookup = find_service_pid(service_name)
    pid = int(service_lookup.get("pid") or 0)
    process: dict = {
        "available": False,
        "service_name": service_name,
        "pid": pid,
        "lookup_method": service_lookup.get("method"),
    }
    if service_lookup.get("error"):
        process["lookup_error"] = service_lookup["error"]
    if pid > 0:
        status = read_proc_status(pid, proc_root)
        if status:
            rss = int(status.get("vmrss_bytes") or 0)
            peak = int(status.get("vmhwm_bytes") or 0)
            warn_bytes = int(warn_mb) * 1024 * 1024
            critical_bytes = int(critical_mb) * 1024 * 1024
            if rss >= critical_bytes or peak >= critical_bytes:
                status_name = "critical"
            elif rss >= warn_bytes or peak >= warn_bytes:
                status_name = "warning"
            else:
                status_name = "ok"
            process.update({
                "available": True,
                "status": status_name,
                "rss_bytes": rss,
                "peak_rss_bytes": peak,
                "vm_size_bytes": int(status.get("vmsize_bytes") or 0),
                "data_bytes": int(status.get("vmdata_bytes") or 0),
                "swap_bytes": int(status.get("vmswap_bytes") or 0),
                "threads": int(status.get("threads") or 0),
                "fd_count": count_proc_fds(pid, proc_root),
                "cmdline": read_proc_cmdline(pid, proc_root)[:500],
                "warn_bytes": warn_bytes,
                "critical_bytes": critical_bytes,
            })
        else:
            process["status"] = "unknown"
            process["error"] = f"/proc/{pid}/status unavailable"
    else:
        process["status"] = "unknown"
    return {
        "service": process,
        "system": system,
        "top_processes": scan_process_memory(proc_root, top_processes),
    }


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        if item.is_file():
            total += file_size(item)
    return total


def unique_dir_size(path: Path) -> int:
    total = 0
    seen: set[tuple[int, int]] = set()
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        key = (stat.st_dev, stat.st_ino)
        if key in seen:
            continue
        seen.add(key)
        total += stat.st_size
    return total


def count_files(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += 1
    return total


def disk_report(paths: Iterable[Path]) -> list[dict]:
    seen: set[Path] = set()
    rows: list[dict] = []
    for path in paths:
        if not path.exists():
            rows.append({"path": str(path), "exists": False})
            continue
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        usage = shutil.disk_usage(path)
        rows.append({
            "path": str(path),
            "exists": True,
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_percent": round(usage.used / usage.total * 100, 2) if usage.total else 0,
        })
    return rows


def health_check(url: str, timeout_seconds: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as resp:
            body = resp.read(256).decode("utf-8", errors="replace")
            return {"ok": 200 <= resp.status < 300, "status_code": resp.status, "body": body}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - report script should capture all health errors.
        return {"ok": False, "status_code": 0, "error": str(exc)}


def json_endpoint_check(url: str, timeout_seconds: float, max_bytes: int = 1024 * 1024) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as resp:
            raw = resp.read(max_bytes)
            body = raw.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body) if body else {}
            except json.JSONDecodeError as exc:
                return {
                    "ok": False,
                    "status_code": resp.status,
                    "error": f"invalid json: {exc}",
                    "body": body[:500],
                }
            return {"ok": 200 <= resp.status < 300, "status_code": resp.status, "body": parsed}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - report script should not fail the whole run.
        return {"ok": False, "status_code": 0, "error": str(exc)}


def classify_task_error(error: str) -> str:
    text = error or ""
    if not text.strip():
        return "no_error_text"
    for name, pattern in TASK_ERROR_PATTERNS.items():
        if pattern.search(text):
            return name
    return "unknown"


def list_user_db_paths(data_dir: Path) -> list[Path]:
    paths = [data_dir / "game_video.db"]
    users_dir = data_dir / "users"
    if users_dir.exists():
        paths.extend(sorted(users_dir.glob("*/database.db")))
    return [path for path in paths if path.exists()]


def connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def db_task_report(data_dir: Path, hours: int) -> dict:
    db_paths = list_user_db_paths(data_dir)
    since = since_iso(hours)
    stale_processing_cutoff = since_iso(2)
    status_total: Counter[str] = Counter()
    status_recent: Counter[str] = Counter()
    provider_recent: Counter[str] = Counter()
    model_recent: Counter[str] = Counter()
    failed_recent_by_provider: Counter[str] = Counter()
    failed_recent_by_model: Counter[str] = Counter()
    error_categories: Counter[str] = Counter()
    error_category_by_provider: dict[str, Counter[str]] = defaultdict(Counter)
    stale_processing_by_provider: Counter[str] = Counter()
    recent_errors: list[dict] = []
    stale_processing_sample: list[dict] = []
    db_errors: list[dict] = []
    operation_events: Counter[str] = Counter()

    for db_path in db_paths:
        try:
            conn = connect_readonly(db_path)
        except sqlite3.Error as exc:
            db_errors.append({"db": str(db_path), "error": str(exc)})
            continue
        try:
            if table_exists(conn, "game_tasks"):
                for row in conn.execute("SELECT status, COUNT(*) AS count FROM game_tasks GROUP BY status"):
                    status_total[row["status"] or "unknown"] += int(row["count"])
                recent_rows = conn.execute(
                    """
                    SELECT id, status, provider, model, error, created_at, updated_at
                    FROM game_tasks
                    WHERE created_at >= ? OR updated_at >= ?
                    """,
                    (since, since),
                ).fetchall()
                for row in recent_rows:
                    status = row["status"] or "unknown"
                    provider = row["provider"] or "unknown"
                    model = row["model"] or "unknown"
                    status_recent[status] += 1
                    provider_recent[provider] += 1
                    model_recent[model] += 1
                    if status in {"failed", "error", "timeout"}:
                        failed_recent_by_provider[provider] += 1
                        failed_recent_by_model[model] += 1
                        category = classify_task_error(str(row["error"] or ""))
                        error_categories[category] += 1
                        error_category_by_provider[provider][category] += 1
                        if row["error"] and len(recent_errors) < 20:
                            recent_errors.append({
                                "db": str(db_path),
                                "task_id": row["id"],
                                "provider": provider,
                                "model": model,
                                "category": category,
                                "error": str(row["error"])[:500],
                                "updated_at": row["updated_at"],
                            })
                stale_count_rows = conn.execute(
                    """
                    SELECT provider, COUNT(*) AS count
                    FROM game_tasks
                    WHERE status='processing' AND updated_at < ?
                    GROUP BY provider
                    """,
                    (stale_processing_cutoff,),
                ).fetchall()
                for row in stale_count_rows:
                    stale_processing_by_provider[row["provider"] or "unknown"] += int(row["count"])

                stale_rows = conn.execute(
                    """
                    SELECT id, provider, model, created_at, updated_at
                    FROM game_tasks
                    WHERE status='processing' AND updated_at < ?
                    ORDER BY updated_at ASC
                    LIMIT 20
                    """,
                    (stale_processing_cutoff,),
                ).fetchall()
                for row in stale_rows:
                    if len(stale_processing_sample) < 20:
                        stale_processing_sample.append({
                            "db": str(db_path),
                            "task_id": row["id"],
                            "provider": row["provider"] or "unknown",
                            "model": row["model"] or "unknown",
                            "created_at": row["created_at"],
                            "updated_at": row["updated_at"],
                        })
            if table_exists(conn, "game_operation_events"):
                rows = conn.execute(
                    """
                    SELECT status, COUNT(*) AS count
                    FROM game_operation_events
                    WHERE created_at >= ?
                    GROUP BY status
                    """,
                    (since,),
                ).fetchall()
                for row in rows:
                    operation_events[row["status"] or "unknown"] += int(row["count"])
        except sqlite3.Error as exc:
            db_errors.append({"db": str(db_path), "error": str(exc)})
        finally:
            conn.close()

    return {
        "db_count": len(db_paths),
        "since_hours": hours,
        "since": since,
        "task_status_total": dict(status_total),
        "task_status_recent": dict(status_recent),
        "recent_provider_counts": dict(provider_recent),
        "recent_model_counts": dict(model_recent.most_common(20)),
        "recent_failed_by_provider": dict(failed_recent_by_provider),
        "recent_failed_by_model": dict(failed_recent_by_model.most_common(20)),
        "recent_error_categories": dict(error_categories),
        "recent_error_category_by_provider": {
            provider: dict(counter)
            for provider, counter in sorted(error_category_by_provider.items())
        },
        "stale_processing_cutoff": stale_processing_cutoff,
        "stale_processing_by_provider": dict(stale_processing_by_provider),
        "stale_processing_sample": stale_processing_sample,
        "recent_errors_sample": recent_errors,
        "operation_events_recent": dict(operation_events),
        "db_errors": db_errors,
    }


def count_log_error_patterns(lines: list[str]) -> tuple[dict[str, int], dict[str, int], list[str]]:
    error_counts = {name: 0 for name in ERROR_PATTERNS}
    provider_counts = {name: 0 for name in PROVIDER_PATTERNS}
    samples: list[str] = []

    for line in lines:
        matched_error = False
        for name, pattern in ERROR_PATTERNS.items():
            if pattern.search(line):
                error_counts[name] += 1
                matched_error = True
        for name, pattern in PROVIDER_PATTERNS.items():
            if pattern.search(line):
                provider_counts[name] += 1
        if matched_error and len(samples) < 20:
            samples.append(line[-800:])
    return error_counts, provider_counts, samples


def latest_frontend_asset_window(lines: list[str]) -> dict:
    latest_index = -1
    latest_asset = ""
    for index, line in enumerate(lines):
        match = FRONTEND_ASSET_PATTERN.search(line)
        if match:
            latest_index = index
            latest_asset = match.group(0).lstrip("/")
    if latest_index < 0:
        return {
            "asset": "",
            "found": False,
            "lines_after": 0,
            "error_counts_after": {name: 0 for name in ERROR_PATTERNS},
            "samples_after": [],
        }
    post_lines = lines[latest_index + 1:]
    error_counts, _provider_counts, samples = count_log_error_patterns(post_lines)
    return {
        "asset": latest_asset,
        "found": True,
        "lines_after": len(post_lines),
        "error_counts_after": error_counts,
        "samples_after": samples,
    }


def parse_viral_obs_line(line: str) -> dict | None:
    match = VIRAL_OBS_PATTERN.search(line or "")
    if not match:
        return None
    row: dict[str, str | int | float] = {}
    for part in match.group("fields").split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key in {"duration_ms"}:
            try:
                row[key] = float(value)
            except ValueError:
                row[key] = 0.0
        elif key in {"video_count", "tag_count", "plan_count", "target_count", "selected_tag_count", "chinese_retry"}:
            try:
                row[key] = int(value)
            except ValueError:
                row[key] = 0
        else:
            row[key] = value
    if not row.get("operation"):
        return None
    return row


def viral_obs_report(lines: list[str], slow_threshold_ms: int = 30000) -> dict:
    rows = [row for row in (parse_viral_obs_line(line) for line in lines) if row]
    by_operation: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    by_provider: Counter[str] = Counter()
    error_categories: Counter[str] = Counter()
    chinese_retry_by_operation: Counter[str] = Counter()
    durations: dict[str, list[float]] = defaultdict(list)

    for row in rows:
        operation = str(row.get("operation") or "unknown")
        status = str(row.get("status") or "unknown")
        provider = str(row.get("provider") or "unknown")
        duration = float(row.get("duration_ms") or 0)
        by_operation[operation] += 1
        by_status[status] += 1
        by_provider[provider] += 1
        durations[operation].append(duration)
        if int(row.get("chinese_retry") or 0):
            chinese_retry_by_operation[operation] += 1
        if status != "success":
            category = str(row.get("error_category") or "unknown")
            error_categories[category] += 1

    def duration_summary(values: list[float]) -> dict:
        if not values:
            return {"count": 0, "avg_ms": 0, "max_ms": 0}
        return {
            "count": len(values),
            "avg_ms": round(sum(values) / len(values), 1),
            "max_ms": round(max(values), 1),
        }

    slow_samples = [
        row for row in rows
        if float(row.get("duration_ms") or 0) >= slow_threshold_ms
    ]
    slow_samples.sort(key=lambda row: float(row.get("duration_ms") or 0), reverse=True)
    return {
        "sample_count": len(rows),
        "by_operation": dict(by_operation),
        "by_status": dict(by_status),
        "by_provider": dict(by_provider),
        "error_categories": dict(error_categories),
        "chinese_retry_by_operation": dict(chinese_retry_by_operation),
        "duration_by_operation": {
            operation: duration_summary(values)
            for operation, values in sorted(durations.items())
        },
        "slow_samples": slow_samples[:10],
    }


def log_report(app_dir: Path, tail_lines: int) -> dict:
    log_path = app_dir / "app.log"
    if not log_path.exists():
        return {"path": str(log_path), "exists": False}

    lines = read_tail_lines(log_path, tail_lines)
    error_counts, provider_counts, samples = count_log_error_patterns(lines)

    return {
        "path": str(log_path),
        "exists": True,
        "tail_lines": len(lines),
        "file_size_bytes": file_size(log_path),
        "error_counts": error_counts,
        "provider_mentions": provider_counts,
        "viral": viral_obs_report(lines),
        "latest_frontend_asset": latest_frontend_asset_window(lines),
        "samples": samples,
    }


def read_tail_lines(path: Path, max_lines: int) -> list[str]:
    if max_lines <= 0:
        return []
    block_size = 8192
    data = b""
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        position = fh.tell()
        while position > 0 and data.count(b"\n") <= max_lines:
            read_size = min(block_size, position)
            position -= read_size
            fh.seek(position)
            data = fh.read(read_size) + data
    return data.decode("utf-8", errors="replace").splitlines()[-max_lines:]


def backup_report(backup_dir: Path) -> dict:
    full_backups = sorted(backup_dir.glob("game-video-data-*.tar.gz"), key=file_size, reverse=True)
    db_backups = sorted(backup_dir.glob("game-video-dbs-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "backup_dir": str(backup_dir),
        "total_bytes": dir_size(backup_dir),
        "full_backup_count": len(full_backups),
        "full_backup_bytes": sum(file_size(path) for path in full_backups),
        "latest_full_backup": str(full_backups[0]) if full_backups else "",
        "db_backup_count": len(db_backups),
        "latest_db_backup": str(db_backups[0]) if db_backups else "",
        "latest_db_backup_bytes": file_size(db_backups[0]) if db_backups else 0,
    }


def storage_report(data_dir: Path, backup_dir: Path, top_users: int) -> dict:
    users_dir = data_dir / "users"
    user_rows: list[dict] = []
    if users_dir.exists():
        for user_dir in users_dir.iterdir():
            if user_dir.is_dir():
                user_rows.append({
                    "user_dir": user_dir.name,
                    "bytes": dir_size(user_dir),
                    "unique_bytes": unique_dir_size(user_dir),
                    "file_count": count_files(user_dir),
                })
    user_rows.sort(key=lambda row: row["bytes"], reverse=True)
    cloud_dbs_dir = data_dir / "cloud-dbs"
    sizes = {
        "data": dir_size(data_dir),
        "backups": dir_size(backup_dir),
        "users": dir_size(users_dir),
        "global_files": dir_size(data_dir / "files"),
        "cloud_dbs": dir_size(cloud_dbs_dir),
        "auto_db_backups": dir_size(data_dir / "backups" / "auto"),
    }
    unique_sizes = {
        "data": unique_dir_size(data_dir),
        "backups": unique_dir_size(backup_dir),
        "users": unique_dir_size(users_dir),
        "global_files": unique_dir_size(data_dir / "files"),
        "cloud_dbs": unique_dir_size(cloud_dbs_dir),
        "auto_db_backups": unique_dir_size(data_dir / "backups" / "auto"),
    }
    return {
        "data_dir": str(data_dir),
        "backup_dir": str(backup_dir),
        "sizes": sizes,
        "unique_sizes": unique_sizes,
        "hardlink_savings_bytes": max(0, sizes["data"] - unique_sizes["data"]),
        "cloud_dbs_count": len(list(cloud_dbs_dir.glob("*.db"))) if cloud_dbs_dir.exists() else 0,
        "top_user_dirs": user_rows[:top_users],
    }


def recommendations(payload: dict, args: argparse.Namespace) -> list[str]:
    rows: list[str] = []
    for disk in payload["disk"]:
        if not disk.get("exists"):
            continue
        used_percent = float(disk.get("used_percent", 0))
        free_bytes = int(disk.get("free_bytes", 0))
        if used_percent >= args.disk_block_percent or free_bytes < args.disk_min_free_gb * 1024**3:
            rows.append("BLOCK: disk is over the release safety threshold; pause deployments and large batch generations.")
        elif used_percent >= args.disk_warn_percent:
            rows.append("WARN: disk is above the warning threshold; review cleanup reports before the next release.")

    backup = payload["backups"]
    if backup["full_backup_count"] > 1:
        rows.append("Keep only the latest local full media backup; move older full backups off the system disk.")

    if payload["storage"]["cloud_dbs_count"] > args.cloud_dbs_keep_count:
        rows.append(f"cloud-dbs exceeds keep count {args.cloud_dbs_keep_count}; review dry-run before cleanup.")

    task_recent = payload["tasks"].get("task_status_recent", {})
    failed_recent = sum(count for status, count in task_recent.items() if status in {"failed", "error", "timeout"})
    if failed_recent:
        rows.append(f"Recent task failures detected: {failed_recent}; inspect provider error distribution.")

    log_counts = payload["logs"].get("error_counts", {})
    if log_counts.get("http_429", 0):
        rows.append("Recent 429 signals detected in app log; review key pool and provider queue pressure.")
    if log_counts.get("http_503", 0) or log_counts.get("http_504", 0):
        rows.append("Recent upstream 503/504 signals detected; separate provider instability from local failures.")
    viral = payload["logs"].get("viral") or {}
    viral_errors = viral.get("error_categories") or {}
    if viral_errors:
        rows.append(f"Viral workbench model failures detected: {viral_errors}.")
    viral_slow_samples = viral.get("slow_samples") or []
    if viral_slow_samples:
        rows.append(f"Viral workbench slow operations detected: {len(viral_slow_samples)} samples above threshold.")

    provider_queue = payload.get("provider_queue", {})
    if provider_queue.get("ok"):
        snapshot = provider_queue.get("body", {}).get("snapshot", {})
        providers = snapshot.get("providers", {})
        saturated = [
            key for key, row in providers.items()
            if row.get("saturated") or int(row.get("waiting") or 0) > 0
        ]
        if saturated:
            rows.append(f"Provider queue pressure detected: {', '.join(saturated)}.")
        key_pools = snapshot.get("key_pools", {})
        cooling_pools = [
            key for key, row in key_pools.items()
            if int(row.get("key_count") or 0) > 0
            and int(row.get("cooling_down_count") or 0) >= int(row.get("key_count") or 0)
        ]
        if cooling_pools:
            rows.append(f"All Gemini keys are cooling down for: {', '.join(cooling_pools)}.")
        timed_out_pools = [
            key for key, row in key_pools.items()
            if int(row.get("project", {}).get("total_queue_timeouts") or 0) > 0
        ]
        if timed_out_pools:
            rows.append(f"Gemini project queue timeouts detected for: {', '.join(timed_out_pools)}.")
        status_queries = snapshot.get("status_queries", {}).get("providers", {})
        pressured_status_queries = [
            key for key, row in status_queries.items()
            if row.get("saturated") or int(row.get("waiting") or 0) > 0 or int(row.get("total_timeouts") or 0) > 0
        ]
        if pressured_status_queries:
            rows.append(f"Provider status-query pressure detected: {', '.join(pressured_status_queries)}.")
    else:
        rows.append("Provider queue snapshot unavailable; check local /ops/provider-queue endpoint after deployment.")

    memory = payload.get("memory", {})
    service_memory = memory.get("service", {})
    memory_status = service_memory.get("status")
    if memory_status == "critical":
        rows.append(
            "BLOCK: service memory is above the critical threshold; inspect hot paths before large batch usage."
        )
    elif memory_status == "warning":
        rows.append("WARN: service memory is above the warning threshold; inspect recent workload and log samples.")
    if service_memory.get("available"):
        rss = int(service_memory.get("rss_bytes") or 0)
        peak = int(service_memory.get("peak_rss_bytes") or 0)
        if peak > rss * 2 and peak - rss > 256 * 1024 * 1024:
            rows.append("Peak memory is much higher than current RSS; review bursty video/image processing paths.")
    else:
        rows.append("Service memory snapshot unavailable; run the report on the production host with /proc access.")

    if not rows:
        rows.append("No immediate blocker found by this read-only report.")

    return rows


def build_report(args: argparse.Namespace) -> dict:
    payload = {
        "action": "health_report",
        "created_at": now_iso(),
        "health": health_check(args.health_url, args.health_timeout_seconds),
        "provider_queue": json_endpoint_check(args.provider_queue_url, args.provider_queue_timeout_seconds),
        "disk": disk_report([args.data_dir, args.backup_dir, args.app_dir]),
        "storage": storage_report(args.data_dir, args.backup_dir, args.top_users),
        "backups": backup_report(args.backup_dir),
        "tasks": db_task_report(args.data_dir, args.since_hours),
        "logs": log_report(args.app_dir, args.log_tail_lines),
        "memory": memory_report(
            args.service_name,
            args.memory_warn_mb,
            args.memory_critical_mb,
            args.top_memory_processes,
        ),
        "thresholds": {
            "disk_warn_percent": args.disk_warn_percent,
            "disk_block_percent": args.disk_block_percent,
            "disk_min_free_gb": args.disk_min_free_gb,
            "cloud_dbs_keep_count": args.cloud_dbs_keep_count,
            "memory_warn_mb": args.memory_warn_mb,
            "memory_critical_mb": args.memory_critical_mb,
        },
    }
    payload["recommendations"] = recommendations(payload, args)
    return payload


def write_json(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_summary(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"health_ok: {payload['health'].get('ok')}")
    for disk in payload["disk"]:
        if disk.get("exists"):
            print(f"disk {disk['path']}: {disk['used_percent']}% used, {human_size(int(disk['free_bytes']))} free")
    unique_sizes = payload["storage"].get("unique_sizes", {})
    for name, size in payload["storage"]["sizes"].items():
        unique = unique_sizes.get(name)
        if unique is None:
            print(f"{name}: {human_size(int(size))}")
        else:
            print(f"{name}: logical {human_size(int(size))}, unique {human_size(int(unique))}")
    print(f"hardlink_savings: {human_size(int(payload['storage'].get('hardlink_savings_bytes', 0)))}")
    print(f"cloud_dbs_count: {payload['storage']['cloud_dbs_count']}")
    print(f"full_backups: {payload['backups']['full_backup_count']} / {human_size(int(payload['backups']['full_backup_bytes']))}")
    print(f"db_backups: {payload['backups']['db_backup_count']}")
    print(f"task_status_recent: {payload['tasks']['task_status_recent']}")
    print(f"recent_error_categories: {payload['tasks'].get('recent_error_categories', {})}")
    print(f"stale_processing_by_provider: {payload['tasks'].get('stale_processing_by_provider', {})}")
    viral_obs = payload["logs"].get("viral") or {}
    if viral_obs.get("sample_count"):
        print(
            "viral_observability: "
            f"samples={viral_obs.get('sample_count')} "
            f"operations={viral_obs.get('by_operation', {})} "
            f"status={viral_obs.get('by_status', {})} "
            f"errors={viral_obs.get('error_categories', {})} "
            f"retries={viral_obs.get('chinese_retry_by_operation', {})}"
        )
    provider_queue = payload.get("provider_queue", {})
    if provider_queue.get("ok"):
        snapshot = provider_queue.get("body", {}).get("snapshot", {})
        providers = snapshot.get("providers", {})
        queue_rows = {
            key: {
                "active": row.get("active"),
                "waiting": row.get("waiting"),
                "limit": row.get("limit"),
                "total_timeouts": row.get("total_timeouts"),
            }
            for key, row in providers.items()
        }
        print(f"provider_queue: {queue_rows}")
        key_pools = snapshot.get("key_pools", {})
        key_pool_rows = {
            key: {
                "key_count": row.get("key_count"),
                "cooling_down_count": row.get("cooling_down_count"),
                "project_active": row.get("project", {}).get("active"),
                "project_waiting": row.get("project", {}).get("waiting"),
                "project_limit": row.get("project", {}).get("limit"),
                "project_timeouts": row.get("project", {}).get("total_queue_timeouts"),
            }
            for key, row in key_pools.items()
        }
        print(f"gemini_key_pools: {key_pool_rows}")
        status_queries = snapshot.get("status_queries", {}).get("providers", {})
        status_query_rows = {
            key: {
                "active": row.get("active"),
                "waiting": row.get("waiting"),
                "limit": row.get("limit"),
                "inflight": row.get("inflight"),
                "cache_entries": row.get("cache_entries"),
                "cache_hits": row.get("total_cache_hits"),
                "coalesced": row.get("total_coalesced"),
                "timeouts": row.get("total_timeouts"),
            }
            for key, row in status_queries.items()
        }
        print(f"status_queries: {status_query_rows}")
    else:
        print(f"provider_queue_error: {provider_queue.get('error') or provider_queue.get('status_code')}")
    memory = payload.get("memory", {})
    service_memory = memory.get("service", {})
    if service_memory.get("available"):
        print(
            "memory_service: "
            f"pid={service_memory.get('pid')} "
            f"status={service_memory.get('status')} "
            f"rss={human_size(int(service_memory.get('rss_bytes') or 0))} "
            f"peak={human_size(int(service_memory.get('peak_rss_bytes') or 0))} "
            f"threads={service_memory.get('threads')} "
            f"fds={service_memory.get('fd_count')}"
        )
    else:
        print(f"memory_service: unavailable status={service_memory.get('status')} error={service_memory.get('lookup_error') or service_memory.get('error')}")
    system_memory = memory.get("system", {})
    if system_memory.get("available"):
        print(
            "memory_system: "
            f"used={system_memory.get('memory_used_percent')}% "
            f"available={human_size(int(system_memory.get('memavailable_bytes') or 0))} "
            f"total={human_size(int(system_memory.get('memtotal_bytes') or 0))}"
        )
    top_processes = memory.get("top_processes") or []
    if top_processes:
        top_rows = [
            {
                "pid": row.get("pid"),
                "name": row.get("name"),
                "rss": human_size(int(row.get("rss_bytes") or 0)),
                "threads": row.get("threads"),
            }
            for row in top_processes[:5]
        ]
        print(f"top_memory_processes: {top_rows}")
    print(f"log_error_counts: {payload['logs'].get('error_counts', {})}")
    latest_asset = payload["logs"].get("latest_frontend_asset") or {}
    if latest_asset.get("found"):
        print(f"latest_frontend_asset: {latest_asset.get('asset')} lines_after={latest_asset.get('lines_after')} errors_after={latest_asset.get('error_counts_after', {})}")
    print("recommendations:")
    for row in payload["recommendations"]:
        print(f"- {row}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only production health report")
    parser.add_argument("--app-dir", type=Path, default=DEFAULT_APP_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--health-timeout-seconds", type=float, default=3)
    parser.add_argument("--provider-queue-url", default=DEFAULT_PROVIDER_QUEUE_URL)
    parser.add_argument("--provider-queue-timeout-seconds", type=float, default=3)
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--since-hours", type=int, default=24)
    parser.add_argument("--log-tail-lines", type=int, default=5000)
    parser.add_argument("--top-users", type=int, default=10)
    parser.add_argument("--top-memory-processes", type=int, default=8)
    parser.add_argument("--cloud-dbs-keep-count", type=int, default=200)
    parser.add_argument("--disk-warn-percent", type=int, default=70)
    parser.add_argument("--disk-block-percent", type=int, default=90)
    parser.add_argument("--disk-min-free-gb", type=float, default=5)
    parser.add_argument("--memory-warn-mb", type=int, default=1200)
    parser.add_argument("--memory-critical-mb", type=int, default=1600)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(args)
    write_json(args.json_report, payload)
    print_summary(payload)
    if not payload["health"].get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
