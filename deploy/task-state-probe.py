#!/usr/bin/env python3
"""Read-only external status probe for stale video tasks.

The probe calls provider status APIs for sampled stale tasks and reports what
the provider currently says. It never updates SQLite, downloads videos, caches
media, or changes billing records.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_DATA_DIR = Path(os.environ.get("GAME_VIDEO_DATA_DIR", "/home/deploy/game-video-data"))
DEFAULT_BACKUP_DIR = Path(os.environ.get("GAME_VIDEO_BACKUP_DIR", "/home/deploy/game-video-backups"))
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
SEEDANCE_PROVIDERS = {"jimeng", "seedance", "ark"}
WAN_PROVIDERS = {"wan"}
HAPPYHORSE_PROVIDERS = {"happyhorse"}
RECOVERABLE_FAILED_ERROR_CATEGORIES = {
    "provider_result_unavailable",
    "provider_video_missing_url",
    "provider_video_remote_http_403",
    "provider_video_remote_http_404",
    "provider_video_remote_http_5xx",
    "provider_video_empty_download",
    "provider_video_local_write_failed",
    "provider_video_unknown_cache_error",
}


def now_iso() -> str:
    task_audit = load_task_audit_module()
    return task_audit.now_iso()


def load_task_audit_module():
    path = Path(__file__).with_name("task-state-audit.py")
    spec = importlib.util.spec_from_file_location("task_state_audit_runtime", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


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


def redact_secret(value: str) -> str:
    text = str(value or "")
    if len(text) <= 8:
        return "***" if text else ""
    return f"{text[:4]}...{text[-4:]}"


def select_provider_candidates(
    audit_payload: dict,
    providers: set[str],
    limit: int,
    task_ids: set[str] | None = None,
) -> list[dict]:
    candidates: list[dict] = []
    for item in audit_payload.get("stale_processing_sample", []):
        provider = (item.get("provider") or "").lower()
        external_task_id = item.get("external_task_id") or ""
        task_id = item.get("task_id") or ""
        if provider not in providers:
            continue
        if not external_task_id:
            continue
        if task_ids and task_id not in task_ids and external_task_id not in task_ids:
            continue
        candidates.append(item)
        if len(candidates) >= limit:
            break
    return candidates


def select_seedance_candidates(audit_payload: dict, limit: int, task_ids: set[str] | None = None) -> list[dict]:
    return select_provider_candidates(audit_payload, SEEDANCE_PROVIDERS, limit, task_ids)


def select_wan_candidates(audit_payload: dict, limit: int, task_ids: set[str] | None = None) -> list[dict]:
    return select_provider_candidates(audit_payload, WAN_PROVIDERS, limit, task_ids)


def select_happyhorse_candidates(audit_payload: dict, limit: int, task_ids: set[str] | None = None) -> list[dict]:
    return select_provider_candidates(audit_payload, HAPPYHORSE_PROVIDERS, limit, task_ids)


def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    rows: list[dict] = []
    for item in candidates:
        key = (
            str(item.get("user_id") or ""),
            str(item.get("task_id") or ""),
            str(item.get("external_task_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(item)
    return rows


def select_explicit_failed_candidates(
    data_dir: Path,
    task_audit,
    task_ids: set[str],
    limit: int,
) -> list[dict]:
    if not task_ids or limit <= 0:
        return []
    users = task_audit.load_user_index(data_dir)
    rows: list[dict] = []
    for db_path in task_audit.list_user_db_paths(data_dir):
        user_id = task_audit.user_id_from_db_path(data_dir, db_path)
        user = users.get(user_id, {})
        try:
            conn = task_audit.connect_readonly(db_path)
        except sqlite3.Error:
            continue
        try:
            if not task_audit.table_exists(conn, "game_tasks"):
                continue
            for task_id in sorted(task_ids):
                row = conn.execute(
                    """
                    SELECT id, project_id, type, prompt, provider, model, status,
                           external_task_id, video_url, error, created_at, updated_at
                    FROM game_tasks
                    WHERE status='failed'
                      AND COALESCE(video_url, '')=''
                      AND (id=? OR external_task_id=?)
                    LIMIT 1
                    """,
                    (task_id, task_id),
                ).fetchone()
                if not row:
                    continue
                item = dict(row)
                provider = (item.get("provider") or "").lower()
                if (
                    provider not in SEEDANCE_PROVIDERS
                    and provider not in WAN_PROVIDERS
                    and provider not in HAPPYHORSE_PROVIDERS
                ):
                    continue
                if not item.get("external_task_id"):
                    continue
                error_category = task_audit.classify_task_error(item.get("error", ""))
                if error_category not in RECOVERABLE_FAILED_ERROR_CATEGORIES:
                    continue
                project_names = task_audit.fetch_project_names(conn, [item.get("project_id", "")])
                rows.append({
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
                    "status": "failed",
                    "external_task_id": item.get("external_task_id", ""),
                    "has_video_url": bool(item.get("video_url")),
                    "has_error": bool(item.get("error")),
                    "error_category": error_category,
                    "prompt_preview": task_audit.preview_text(item.get("prompt"), 120),
                    "created_at": item.get("created_at", ""),
                    "updated_at": item.get("updated_at", ""),
                    "candidate_action": "query_provider_status_for_failed_result_recovery",
                })
                if len(rows) >= limit:
                    return rows
        except sqlite3.Error:
            continue
        finally:
            conn.close()
    return rows


def probe_row_from_item(item: dict, result: dict, external_task_id: str) -> dict:
    return {
        "db": item.get("db", ""),
        "task_id": item.get("task_id", ""),
        "external_task_id": external_task_id,
        "user_id": item.get("user_id", ""),
        "username": item.get("username", ""),
        "display_name": item.get("display_name", ""),
        "team": item.get("team", ""),
        "project_id": item.get("project_id", ""),
        "project_name": item.get("project_name", ""),
        "provider": item.get("provider", ""),
        "model": item.get("model", ""),
        "local_status": item.get("status", "processing") or "processing",
        "local_updated_at": item.get("updated_at", ""),
        "local_created_at": item.get("created_at", ""),
        "provider_status": result.get("status", ""),
        "raw_status": result.get("raw_status", ""),
        "has_provider_video_url": bool(result.get("video_url")),
        "provider_video_url": result.get("video_url", ""),
        "provider_error": result.get("error", ""),
        "recommended_action": recommended_action_from_probe(result),
    }


async def query_seedance_statuses(candidates: list[dict], api_key: str, concurrency: int) -> list[dict]:
    semaphore = asyncio.Semaphore(max(1, int(concurrency or 1)))

    async def _query(item: dict) -> dict:
        external_task_id = item.get("external_task_id", "")
        async with semaphore:
            try:
                result = await asyncio.to_thread(query_seedance_task, api_key, external_task_id)
                return probe_row_from_item(item, result, external_task_id)
            except Exception as exc:  # noqa: BLE001 - report probe failures.
                result = {
                    "status": "probe_error",
                    "raw_status": "",
                    "video_url": "",
                    "error": str(exc)[:500],
                }
                row = probe_row_from_item(item, result, external_task_id)
                row["recommended_action"] = "do_not_modify_until_probe_succeeds"
                return row

    return await asyncio.gather(*[_query(item) for item in candidates])


async def query_wan_statuses(candidates: list[dict], api_key: str, concurrency: int) -> list[dict]:
    semaphore = asyncio.Semaphore(max(1, int(concurrency or 1)))

    async def _query(item: dict) -> dict:
        external_task_id = item.get("external_task_id", "")
        async with semaphore:
            try:
                result = await asyncio.to_thread(query_wan_task, api_key, external_task_id)
                return probe_row_from_item(item, result, external_task_id)
            except Exception as exc:  # noqa: BLE001 - report probe failures.
                result = {
                    "status": "probe_error",
                    "raw_status": "",
                    "video_url": "",
                    "error": str(exc)[:500],
                }
                row = probe_row_from_item(item, result, external_task_id)
                row["recommended_action"] = "do_not_modify_until_probe_succeeds"
                return row

    return await asyncio.gather(*[_query(item) for item in candidates])


async def query_happyhorse_statuses(candidates: list[dict], api_key: str, concurrency: int) -> list[dict]:
    semaphore = asyncio.Semaphore(max(1, int(concurrency or 1)))

    async def _query(item: dict) -> dict:
        external_task_id = item.get("external_task_id", "")
        async with semaphore:
            try:
                result = await asyncio.to_thread(query_wan_task, api_key, external_task_id)
                return probe_row_from_item(item, result, external_task_id)
            except Exception as exc:  # noqa: BLE001 - report probe failures.
                result = {
                    "status": "probe_error",
                    "raw_status": "",
                    "video_url": "",
                    "error": str(exc)[:500],
                }
                row = probe_row_from_item(item, result, external_task_id)
                row["recommended_action"] = "do_not_modify_until_probe_succeeds"
                return row

    return await asyncio.gather(*[_query(item) for item in candidates])


def query_seedance_task(api_key: str, task_id: str) -> dict:
    url = f"{BASE_URL}/contents/generations/tasks/{task_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
            status_code = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
        return {
            "task_id": task_id,
            "status": "probe_error",
            "video_url": "",
            "error": f"HTTP {exc.code}: {body[:500]}",
            "raw_status": "",
        }
    except Exception as exc:  # noqa: BLE001 - report probe failures.
        return {
            "task_id": task_id,
            "status": "probe_error",
            "video_url": "",
            "error": str(exc)[:500],
            "raw_status": "",
        }

    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        return {
            "task_id": task_id,
            "status": "probe_error",
            "video_url": "",
            "error": f"HTTP {status_code}: invalid json {body[:300]}",
            "raw_status": "",
        }

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
    status = map_seedance_status(status_raw)
    video_url = extract_ark_video_url(inner)
    error = ""
    if status == "failed":
        error = str(inner.get("error", "") or inner.get("message", "") or "")
        if not error and isinstance(inner.get("content"), dict):
            error = str(inner["content"].get("error", "") or inner["content"].get("message", ""))
    if status == "completed" and not video_url:
        status = "failed"
        error = error or "provider completed without video_url"
    return {
        "task_id": task_id,
        "status": status,
        "video_url": video_url,
        "error": error,
        "raw_status": status_raw,
    }


def query_wan_task(api_key: str, task_id: str) -> dict:
    url = f"{DASHSCOPE_BASE_URL}/tasks/{task_id}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
            status_code = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
        return {
            "task_id": task_id,
            "status": "probe_error",
            "video_url": "",
            "error": f"HTTP {exc.code}: {body[:500]}",
            "raw_status": "",
        }
    except Exception as exc:  # noqa: BLE001 - report probe failures.
        return {
            "task_id": task_id,
            "status": "probe_error",
            "video_url": "",
            "error": str(exc)[:500],
            "raw_status": "",
        }

    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        return {
            "task_id": task_id,
            "status": "probe_error",
            "video_url": "",
            "error": f"HTTP {status_code}: invalid json {body[:300]}",
            "raw_status": "",
        }

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
    return {
        "task_id": task_id,
        "status": status,
        "video_url": video_url,
        "error": error,
        "raw_status": status_raw,
    }


def map_seedance_status(status_raw) -> str:
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


def extract_ark_video_url(inner: dict) -> str:
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


def recommended_action_from_probe(result: dict) -> str:
    status = (result.get("status") or "").lower()
    if status == "completed" and result.get("video_url"):
        return "can_repair_to_completed_after_cache_policy_review"
    if status == "completed":
        return "provider_completed_without_video_url_mark_failed_after_review"
    if status == "failed":
        return "can_repair_to_failed_after_review"
    if status in {"processing", "queued", "pending", ""}:
        return "keep_processing_or_apply_timeout_policy_after_review"
    return "manual_review_required"


def build_recommendations(probes: list[dict], missing_keys: dict[str, bool], candidate_counts: dict[str, int]) -> list[str]:
    rows: list[str] = []
    skipped = [
        provider
        for provider, count in candidate_counts.items()
        if count > 0 and missing_keys.get(provider)
    ]
    if skipped:
        rows.append("Provider API key was not found; provider status probe was skipped for: " + ", ".join(skipped) + ".")
    if not probes:
        rows.append("No eligible Seedance/Jimeng/WAN/HappyHorse stale tasks found for provider probing.")
        return rows
    counts: dict[str, int] = {}
    for row in probes:
        counts[row.get("provider_status") or "unknown"] = counts.get(row.get("provider_status") or "unknown", 0) + 1
    rows.append("Provider probe statuses: " + ", ".join(f"{key}:{value}" for key, value in sorted(counts.items())))
    rows.append("Do not write task status from this report automatically; use it as evidence for a reviewed repair step.")
    return rows


async def run_probe(args: argparse.Namespace) -> dict:
    task_audit = load_task_audit_module()
    audit_payload = task_audit.audit_tasks(args)
    task_ids = set(args.task_id or [])
    explicit_failed_candidates = (
        select_explicit_failed_candidates(args.data_dir, task_audit, task_ids, args.limit)
        if args.include_failed
        else []
    )
    combined_payload = {
        "stale_processing_sample": dedupe_candidates(
            list(audit_payload.get("stale_processing_sample", [])) + explicit_failed_candidates
        )
    }
    seedance_candidates = select_seedance_candidates(combined_payload, args.limit, task_ids or None)
    remaining_limit = max(0, int(args.limit or 0) - len(seedance_candidates))
    wan_candidates = select_wan_candidates(combined_payload, remaining_limit, task_ids or None)
    remaining_limit = max(0, int(args.limit or 0) - len(seedance_candidates) - len(wan_candidates))
    happyhorse_candidates = select_happyhorse_candidates(combined_payload, remaining_limit, task_ids or None)
    candidates = seedance_candidates + wan_candidates + happyhorse_candidates
    seedance_api_key = load_seedance_api_key(args.data_dir)
    dashscope_api_key = load_dashscope_api_key(args.data_dir)
    missing_keys = {
        "seedance": bool(seedance_candidates) and not bool(seedance_api_key),
        "wan": bool(wan_candidates) and not bool(dashscope_api_key),
        "happyhorse": bool(happyhorse_candidates) and not bool(dashscope_api_key),
    }
    probes: list[dict] = []
    if seedance_candidates and seedance_api_key:
        probes.extend(await query_seedance_statuses(seedance_candidates, seedance_api_key, args.concurrency))
    if wan_candidates and dashscope_api_key:
        probes.extend(await query_wan_statuses(wan_candidates, dashscope_api_key, args.concurrency))
    if happyhorse_candidates and dashscope_api_key:
        probes.extend(await query_happyhorse_statuses(happyhorse_candidates, dashscope_api_key, args.concurrency))
    api_key_hint = ", ".join(
        row
        for row in (
            f"seedance={redact_secret(seedance_api_key)}" if seedance_api_key else "",
            f"dashscope={redact_secret(dashscope_api_key)}" if dashscope_api_key else "",
        )
        if row
    )
    return {
        "action": "task_state_probe",
        "readonly": True,
        "dry_run": True,
        "mutates_database": False,
        "downloads_media": False,
        "created_at": now_iso(),
        "data_dir": str(args.data_dir),
        "stale_hours": args.stale_hours,
        "candidate_count": len(candidates),
        "candidate_counts": {
            "seedance": len(seedance_candidates),
            "wan": len(wan_candidates),
            "happyhorse": len(happyhorse_candidates),
            "explicit_failed": len(explicit_failed_candidates),
        },
        "probe_count": len(probes),
        "api_key_present": bool(seedance_api_key or dashscope_api_key),
        "api_key_hint": api_key_hint,
        "api_key_present_by_provider": {
            "seedance": bool(seedance_api_key),
            "wan": bool(dashscope_api_key),
            "happyhorse": bool(dashscope_api_key),
        },
        "audit_summary": {
            "db_count": audit_payload.get("db_count"),
            "user_count": audit_payload.get("user_count"),
            "stale_processing_count": audit_payload.get("stale_processing_count"),
            "stale_processing_by_provider": audit_payload.get("stale_processing_by_provider", {}),
            "stale_processing_by_user": audit_payload.get("stale_processing_by_user", {}),
            "explicit_failed_count": len(explicit_failed_candidates),
            "db_errors": audit_payload.get("db_errors", []),
        },
        "probes": probes,
        "recommendations": build_recommendations(
            probes,
            missing_keys,
            {
                "seedance": len(seedance_candidates),
                "wan": len(wan_candidates),
                "happyhorse": len(happyhorse_candidates),
            },
        ),
    }


def write_json_report(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_summary(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"readonly: {payload['readonly']} dry_run: {payload['dry_run']}")
    print(f"candidate_count: {payload['candidate_count']} probe_count: {payload['probe_count']}")
    print(f"api_key_present: {payload['api_key_present']} api_key_hint: {payload['api_key_hint']}")
    print(f"audit_summary: {payload['audit_summary']}")
    print("recommendations:")
    for row in payload["recommendations"]:
        print(f"- {row}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only provider status probe for stale tasks")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--stale-hours", type=float, default=2)
    parser.add_argument("--since-hours", type=float, default=24)
    parser.add_argument("--sample-limit", type=int, default=50)
    parser.add_argument("--prompt-preview-chars", type=int, default=120)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--task-id", action="append", default=[], help="Limit probe to a local task id or external task id")
    parser.add_argument(
        "--include-failed",
        action="store_true",
        help="With explicit --task-id, also probe recoverable failed local tasks that may have provider results.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = asyncio.run(run_probe(args))
    write_json_report(args.json_report, payload)
    print_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
