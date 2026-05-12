#!/usr/bin/env python3
"""Safely execute an approved media cleanup allowlist.

The default mode is dry-run. Real file removal requires an approved allowlist,
a current successful preflight, exact expected count/byte guards, and a
confirmation token. This script never writes databases or calls application
APIs.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


DEFAULT_DATA_DIR = Path("/home/deploy/game-video-data")


def load_preflight_module():
    path = Path(__file__).with_name("media-cleanup-preflight.py")
    spec = importlib.util.spec_from_file_location("media_cleanup_preflight_for_execute", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{num}B"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_report(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def confirmation_token(expected_count: int, expected_logical_bytes: int) -> str:
    return f"DELETE_MEDIA_CLEANUP_{expected_count}_{expected_logical_bytes}"


def disk_snapshot(path: Path) -> dict:
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "total": int(usage.total),
        "used": int(usage.used),
        "free": int(usage.free),
        "used_human": human_size(int(usage.used)),
        "free_human": human_size(int(usage.free)),
    }


def summarize_preflight(preflight: dict) -> dict:
    return {
        "action": preflight.get("action"),
        "created_at": preflight.get("created_at"),
        "source_allowlist": preflight.get("source_allowlist"),
        "technically_verified": preflight.get("technically_verified"),
        "ready_for_execution": preflight.get("ready_for_execution"),
        "human_review_required": preflight.get("human_review_required"),
        "preflight_errors": preflight.get("preflight_errors") or [],
        "allowlist_count": int(preflight.get("allowlist_count") or 0),
        "verified_count": int(preflight.get("verified_count") or 0),
        "blocked_count": int(preflight.get("blocked_count") or 0),
        "pending_review_count": int(preflight.get("pending_review_count") or 0),
        "verified_logical_bytes": int(preflight.get("verified_logical_bytes") or 0),
        "estimated_unique_inode_bytes": int(preflight.get("estimated_unique_inode_bytes") or 0),
    }


def validate_preflight_report(preflight: dict, allowlist_path: Path, expected_count: int, expected_logical_bytes: int) -> list[str]:
    errors: list[str] = []
    if preflight.get("action") != "media_cleanup_preflight":
        errors.append("preflight_action_must_be_media_cleanup_preflight")
    if preflight.get("dry_run") is not True:
        errors.append("preflight_must_be_dry_run")
    if preflight.get("deletion_enabled") is not False:
        errors.append("preflight_deletion_must_be_disabled")
    if preflight.get("source_allowlist") != str(allowlist_path):
        errors.append("preflight_allowlist_path_mismatch")
    if preflight.get("technically_verified") is not True:
        errors.append("preflight_not_technically_verified")
    if preflight.get("preflight_errors"):
        errors.append("preflight_has_errors")
    if int(preflight.get("verified_count") or 0) != expected_count:
        errors.append("preflight_verified_count_mismatch")
    if int(preflight.get("verified_logical_bytes") or 0) != expected_logical_bytes:
        errors.append("preflight_verified_logical_bytes_mismatch")
    if int(preflight.get("blocked_count") or 0) != 0:
        errors.append("preflight_has_blocked_items")
    return errors


def build_current_preflight(args: argparse.Namespace) -> dict:
    preflight_module = load_preflight_module()
    preflight_args = SimpleNamespace(
        allowlist=args.allowlist,
        data_dir=args.data_dir,
        json_report=None,
        min_age_hours=args.min_age_hours,
        include_all_tables=args.include_all_tables,
    )
    return preflight_module.build_preflight(preflight_args)


def validate_item_for_touch(item: dict, data_dir: Path) -> tuple[list[str], dict]:
    reasons: list[str] = []
    path = Path(item.get("path") or "")
    direct = ((item.get("current") or {}).get("direct_recheck") or {})
    if item.get("status") != "verified":
        reasons.append("preflight_item_not_verified")
    if item.get("reasons"):
        reasons.append("preflight_item_has_reasons")
    if not path.is_absolute():
        reasons.append("path_not_absolute")

    try:
        resolved = path.resolve()
        resolved.relative_to(data_dir.resolve())
    except ValueError:
        reasons.append("path_outside_data_dir")
    except OSError as exc:
        reasons.append("path_resolve_failed")
        direct = {**direct, "resolve_error": str(exc)}

    try:
        stat = path.lstat()
    except OSError as exc:
        reasons.append("path_missing")
        return reasons, {"path": str(path), "error": str(exc), "exists": False}

    current = {
        "path": str(path),
        "exists": True,
        "size": int(stat.st_size),
        "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone().replace(microsecond=0).isoformat(),
        "symlink": path.is_symlink(),
        "regular_file": path.is_file(),
        "direct_recheck": direct,
    }
    if path.is_symlink():
        reasons.append("symlink")
    if not path.is_file():
        reasons.append("not_regular_file")
    if int(stat.st_size) != int(item.get("size") or 0):
        reasons.append("size_changed_after_preflight")
    if current["mtime"] != item.get("mtime"):
        reasons.append("mtime_changed_after_preflight")
    if direct:
        if direct.get("allowed_scope") is not True:
            reasons.append("direct_recheck_outside_media_scope")
        if direct.get("regular_file") is not True:
            reasons.append("direct_recheck_not_regular_file")
        if direct.get("symlink") is True:
            reasons.append("direct_recheck_symlink")
    return sorted(set(reasons)), current


def validate_expected_guards(preflight: dict, args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    if int(args.expected_count) <= 0:
        errors.append("expected_count_must_be_positive")
    if int(args.expected_logical_bytes) <= 0:
        errors.append("expected_logical_bytes_must_be_positive")
    if int(preflight.get("verified_count") or 0) != int(args.expected_count):
        errors.append("current_verified_count_mismatch")
    if int(preflight.get("verified_logical_bytes") or 0) != int(args.expected_logical_bytes):
        errors.append("current_verified_logical_bytes_mismatch")
    return errors


def build_execution_report(args: argparse.Namespace) -> dict:
    started_at = now_iso()
    before_disk = disk_snapshot(args.data_dir)
    input_preflight = load_json(args.preflight_report)
    current_preflight = build_current_preflight(args)
    expected_token = confirmation_token(args.expected_count, args.expected_logical_bytes)

    input_errors = validate_preflight_report(
        input_preflight,
        allowlist_path=args.allowlist,
        expected_count=args.expected_count,
        expected_logical_bytes=args.expected_logical_bytes,
    )
    current_errors = validate_preflight_report(
        current_preflight,
        allowlist_path=args.allowlist,
        expected_count=args.expected_count,
        expected_logical_bytes=args.expected_logical_bytes,
    )
    guard_errors = validate_expected_guards(current_preflight, args)
    if current_preflight.get("ready_for_execution") is not True:
        guard_errors.append("current_preflight_not_ready_for_execution")
    if current_preflight.get("human_review_required"):
        guard_errors.append("human_review_required")

    confirmation_valid = args.confirm_token == expected_token
    if args.execute and not confirmation_valid:
        guard_errors.append("invalid_confirmation_token")

    items: list[dict] = []
    item_blocked = False
    for item in current_preflight.get("items") or []:
        reasons, current = validate_item_for_touch(item, args.data_dir)
        if reasons:
            item_blocked = True
        items.append({
            "candidate_id": item.get("candidate_id", ""),
            "path": item.get("path", ""),
            "size": int(item.get("size") or 0),
            "mtime": item.get("mtime", ""),
            "status": "blocked" if reasons else ("pending_delete" if args.execute else "would_delete"),
            "reasons": reasons,
            "current": current,
        })

    can_execute = not input_errors and not current_errors and not guard_errors and not item_blocked
    deleted_count = 0
    deleted_logical_bytes = 0
    execution_errors: list[str] = []

    if not can_execute:
        for item in items:
            if item["status"] in {"pending_delete", "would_delete"}:
                item["status"] = "verified_but_blocked_by_guards"

    if args.execute and can_execute:
        for item in items:
            path = Path(item["path"])
            try:
                path.unlink()
            except OSError as exc:
                item["status"] = "delete_failed"
                item["reasons"] = [f"delete_failed: {exc}"]
                execution_errors.append(f"{path}: {exc}")
                break
            item["status"] = "deleted"
            deleted_count += 1
            deleted_logical_bytes += int(item.get("size") or 0)
    elif args.execute and not can_execute:
        execution_errors.append("execute_requested_but_safety_checks_failed")

    after_disk = disk_snapshot(args.data_dir)
    return {
        "action": "media_cleanup_execute",
        "dry_run": not args.execute,
        "deletion_enabled": bool(args.execute),
        "executed": bool(args.execute and can_execute and not execution_errors),
        "created_at": started_at,
        "finished_at": now_iso(),
        "data_dir": str(args.data_dir),
        "source_allowlist": str(args.allowlist),
        "source_preflight_report": str(args.preflight_report),
        "expected": {
            "count": int(args.expected_count),
            "logical_bytes": int(args.expected_logical_bytes),
            "confirmation_token": expected_token,
        },
        "execute_requested": bool(args.execute),
        "confirmation_token_valid": confirmation_valid,
        "can_execute": can_execute,
        "input_preflight_errors": input_errors,
        "current_preflight_errors": current_errors,
        "guard_errors": sorted(set(guard_errors)),
        "execution_errors": execution_errors,
        "input_preflight": summarize_preflight(input_preflight),
        "current_preflight": summarize_preflight(current_preflight),
        "before_disk": before_disk,
        "after_disk": after_disk,
        "disk_free_delta_bytes": int(after_disk["free"]) - int(before_disk["free"]),
        "would_delete_count": len(items) if can_execute and not args.execute else 0,
        "would_delete_logical_bytes": sum(int(item.get("size") or 0) for item in items) if can_execute and not args.execute else 0,
        "deleted_count": deleted_count,
        "deleted_logical_bytes": deleted_logical_bytes,
        "estimated_unique_inode_bytes": int(current_preflight.get("estimated_unique_inode_bytes") or 0),
        "items": items,
        "instructions": [
            "Dry-run reports do not remove files.",
            "Real execution requires ready_for_execution=true, approved allowlist rows, exact expected guards, and the confirmation token.",
            "If any safety check fails, no deletion should be attempted.",
        ],
    }


def print_report(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"dry_run: {payload['dry_run']} deletion_enabled: {payload['deletion_enabled']} executed: {payload['executed']}")
    print(f"can_execute: {payload['can_execute']} execute_requested: {payload['execute_requested']}")
    print(f"would_delete: {payload['would_delete_count']} / {human_size(payload['would_delete_logical_bytes'])}")
    print(f"deleted: {payload['deleted_count']} / {human_size(payload['deleted_logical_bytes'])}")
    print(f"estimated_unique_inode_bytes: {human_size(payload['estimated_unique_inode_bytes'])}")
    print(f"input_preflight_errors: {len(payload['input_preflight_errors'])}")
    print(f"current_preflight_errors: {len(payload['current_preflight_errors'])}")
    print(f"guard_errors: {payload['guard_errors']}")
    print(f"execution_errors: {payload['execution_errors']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute an approved media cleanup allowlist with safety guards")
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--expected-logical-bytes", type=int, required=True)
    parser.add_argument("--min-age-hours", type=float, default=None)
    parser.add_argument("--include-all-tables", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-token", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_execution_report(args)
    write_json_report(args.json_report, payload)
    print_report(payload)
    if not args.execute:
        return 0
    return 0 if payload.get("executed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
