#!/usr/bin/env python3
"""Verify a media cleanup allowlist against current read-only scan results.

This tool never removes files. It re-runs the current dry-run cleanup plan and
checks every allowlist row against the latest filesystem and reference state.
Any mismatch blocks the future execution package from using the allowlist.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


DEFAULT_DATA_DIR = Path("/home/deploy/game-video-data")


def load_cleanup_plan_module():
    path = Path(__file__).with_name("media-cleanup-plan.py")
    spec = importlib.util.spec_from_file_location("media_cleanup_plan_for_preflight", path)
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


def allowlist_min_age_hours(allowlist: dict, fallback: float) -> float:
    try:
        return float((allowlist.get("selection") or {}).get("min_age_hours"))
    except (TypeError, ValueError):
        return fallback


def build_current_plan(data_dir: Path, min_age_hours: float, include_all_tables: bool) -> dict:
    cleanup_plan = load_cleanup_plan_module()
    args = SimpleNamespace(
        data_dir=data_dir,
        json_report=None,
        min_age_hours=min_age_hours,
        candidate_limit=0,
        sample_limit=50,
        reference_sample_limit=3,
        include_all_tables=include_all_tables,
    )
    return cleanup_plan.build_plan(args)


def validate_allowlist_header(allowlist: dict) -> list[str]:
    errors: list[str] = []
    if allowlist.get("action") != "media_cleanup_allowlist":
        errors.append("allowlist_action_must_be_media_cleanup_allowlist")
    if allowlist.get("dry_run") is not True:
        errors.append("allowlist_must_be_dry_run")
    if allowlist.get("deletion_enabled") is not False:
        errors.append("allowlist_deletion_must_be_disabled")
    if allowlist.get("preflight_errors"):
        errors.append("allowlist_has_preflight_errors")
    if not isinstance(allowlist.get("allowlist"), list):
        errors.append("allowlist_must_be_a_list")
    return errors


def validate_allowlist_row(row: dict) -> list[str]:
    reasons: list[str] = []
    if not row.get("candidate_id"):
        reasons.append("missing_candidate_id")
    if not row.get("path"):
        reasons.append("missing_path")
    if int(row.get("size") or 0) <= 0:
        reasons.append("invalid_allowlist_size")
    if int(row.get("reference_count") or 0) != 0:
        reasons.append("allowlist_reference_count_not_zero")
    if row.get("reference_kinds") not in ({}, None):
        reasons.append("allowlist_reference_kinds_not_empty")

    expected = row.get("expected") or {}
    if expected:
        if expected.get("path") and expected.get("path") != row.get("path"):
            reasons.append("allowlist_expected_path_mismatch")
        if expected.get("size") is not None and int(expected.get("size") or 0) != int(row.get("size") or 0):
            reasons.append("allowlist_expected_size_mismatch")
        if expected.get("mtime") and expected.get("mtime") != row.get("mtime"):
            reasons.append("allowlist_expected_mtime_mismatch")
        if expected.get("reference_class") and expected.get("reference_class") != "unreferenced":
            reasons.append("allowlist_expected_reference_class_not_unreferenced")
    return reasons


def path_recheck(path_text: str, data_dir: Path, cleanup_plan) -> dict:
    path = Path(path_text)
    recheck = {
        "path_exists": False,
        "regular_file": False,
        "symlink": False,
        "allowed_scope": False,
        "scope": "",
        "user_id": "",
        "size": None,
        "mtime": "",
    }
    scope, user_id, allowed_scope = cleanup_plan.path_scope(path, data_dir)
    recheck["scope"] = scope
    recheck["user_id"] = user_id
    recheck["allowed_scope"] = allowed_scope
    try:
        stat = path.lstat()
    except OSError as exc:
        recheck["error"] = str(exc)
        return recheck

    recheck["path_exists"] = True
    recheck["symlink"] = path.is_symlink()
    recheck["regular_file"] = path.is_file()
    recheck["size"] = int(stat.st_size)
    recheck["mtime"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone().replace(microsecond=0).isoformat()
    return recheck


def validate_against_current(row: dict, current: dict | None, data_dir: Path, cleanup_plan) -> tuple[list[str], dict]:
    reasons: list[str] = []
    current_view: dict = {}
    direct = path_recheck(str(row.get("path") or ""), data_dir, cleanup_plan)

    if not direct["path_exists"]:
        reasons.append("path_missing")
    if direct["path_exists"] and not direct["regular_file"]:
        reasons.append("not_regular_file")
    if direct["symlink"]:
        reasons.append("symlink")
    if not direct["allowed_scope"]:
        reasons.append("outside_media_scope")

    if current is None:
        reasons.append("not_in_current_cleanup_plan")
        current_view["direct_recheck"] = direct
        return reasons, current_view

    current_view = {
        "candidate_id": current.get("candidate_id"),
        "path": current.get("path"),
        "size": current.get("size"),
        "mtime": current.get("mtime"),
        "reference_count": current.get("reference_count"),
        "reference_kinds": current.get("reference_kinds") or {},
        "recheck": current.get("recheck") or {},
        "direct_recheck": direct,
    }
    if current.get("candidate_id") != row.get("candidate_id"):
        reasons.append("candidate_id_changed")
    if current.get("path") != row.get("path"):
        reasons.append("path_changed")
    if int(current.get("size") or 0) != int(row.get("size") or 0):
        reasons.append("size_changed")
    if current.get("mtime") != row.get("mtime"):
        reasons.append("mtime_changed")
    if int(current.get("reference_count") or 0) != 0:
        reasons.append("current_reference_count_not_zero")
    if (current.get("reference_kinds") or {}) != {}:
        reasons.append("current_reference_kinds_not_empty")

    recheck = current.get("recheck") or {}
    if recheck.get("reference_class") != "unreferenced":
        reasons.append("current_reference_class_not_unreferenced")
    if recheck.get("path_exists") is not True:
        reasons.append("current_path_not_confirmed")
    if recheck.get("regular_file") is not True:
        reasons.append("current_not_regular_file")
    if recheck.get("symlink") is True:
        reasons.append("current_symlink")
    if recheck.get("allowed_scope") is not True:
        reasons.append("current_outside_media_scope")
    return reasons, current_view


def estimate_unique_inode_bytes(items: list[dict]) -> int:
    seen: set[tuple[int, int]] = set()
    total = 0
    for item in items:
        if item.get("status") != "verified":
            continue
        path = Path(item["path"])
        try:
            stat = path.stat()
        except OSError:
            continue
        key = (stat.st_dev, stat.st_ino)
        if key in seen:
            continue
        seen.add(key)
        total += int(stat.st_size)
    return total


def build_preflight(args: argparse.Namespace) -> dict:
    allowlist = load_json(args.allowlist)
    preflight_errors = validate_allowlist_header(allowlist)
    min_age_hours = args.min_age_hours
    if min_age_hours is None:
        min_age_hours = allowlist_min_age_hours(allowlist, fallback=72.0)

    current_plan = build_current_plan(
        data_dir=args.data_dir,
        min_age_hours=float(min_age_hours),
        include_all_tables=args.include_all_tables,
    )
    if current_plan.get("dry_run") is not True:
        preflight_errors.append("current_plan_must_be_dry_run")
    if current_plan.get("deletion_enabled") is not False:
        preflight_errors.append("current_plan_deletion_must_be_disabled")
    if current_plan.get("reference_db_errors"):
        preflight_errors.append("current_plan_has_reference_db_errors")

    cleanup_plan = load_cleanup_plan_module()
    candidates = current_plan.get("candidates") or []
    by_id = {row.get("candidate_id"): row for row in candidates if row.get("candidate_id")}
    by_path = {row.get("path"): row for row in candidates if row.get("path")}

    items: list[dict] = []
    for row in allowlist.get("allowlist") or []:
        row_reasons = validate_allowlist_row(row)
        current = by_id.get(row.get("candidate_id"))
        if current is None and row.get("path") in by_path:
            current = by_path[row.get("path")]
        current_reasons, current_view = validate_against_current(row, current, args.data_dir, cleanup_plan)
        reasons = sorted(set(row_reasons + current_reasons))
        items.append({
            "candidate_id": row.get("candidate_id", ""),
            "path": row.get("path", ""),
            "size": int(row.get("size") or 0),
            "mtime": row.get("mtime", ""),
            "status": "blocked" if reasons else "verified",
            "reasons": reasons,
            "allowlist": {
                "reference_count": int(row.get("reference_count") or 0),
                "reference_kinds": row.get("reference_kinds") or {},
                "review_status": row.get("review_status", ""),
                "expected": row.get("expected") or {},
            },
            "current": current_view,
        })

    verified = [item for item in items if item["status"] == "verified"]
    blocked = [item for item in items if item["status"] == "blocked"]
    pending_review = [
        item for item in verified
        if (item.get("allowlist") or {}).get("review_status") != "approved"
    ]
    technically_verified = not preflight_errors and bool(items) and not blocked
    ready = technically_verified and not pending_review
    return {
        "action": "media_cleanup_preflight",
        "dry_run": True,
        "deletion_enabled": False,
        "created_at": now_iso(),
        "data_dir": str(args.data_dir),
        "source_allowlist": str(args.allowlist),
        "source_allowlist_created_at": allowlist.get("created_at", ""),
        "current_plan": {
            "created_at": current_plan.get("created_at", ""),
            "candidate_count": int(current_plan.get("candidate_count") or 0),
            "candidate_logical_bytes": int(current_plan.get("candidate_logical_bytes") or 0),
            "estimated_reclaim_bytes": int(current_plan.get("estimated_reclaim_bytes") or 0),
            "reference_db_errors": current_plan.get("reference_db_errors") or [],
            "min_age_hours": current_plan.get("min_age_hours"),
        },
        "technically_verified": technically_verified,
        "ready_for_execution": ready,
        "human_review_required": bool(pending_review),
        "preflight_errors": preflight_errors,
        "allowlist_count": len(allowlist.get("allowlist") or []),
        "verified_count": len(verified),
        "blocked_count": len(blocked),
        "pending_review_count": len(pending_review),
        "verified_logical_bytes": sum(int(item.get("size") or 0) for item in verified),
        "estimated_unique_inode_bytes": estimate_unique_inode_bytes(verified),
        "blocked_by_reason": {
            reason: sum(1 for item in blocked if reason in item.get("reasons", []))
            for reason in sorted({reason for item in blocked for reason in item.get("reasons", [])})
        },
        "items": items,
        "instructions": [
            "This report is read-only and cannot remove files.",
            "A future execution package must accept only ready_for_execution=true reports and must re-run this preflight immediately before touching files.",
            "Blocked items require a new cleanup plan and allowlist review before any future action.",
        ],
    }


def print_report(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"dry_run: {payload['dry_run']} deletion_enabled: {payload['deletion_enabled']}")
    print(f"technically_verified: {payload['technically_verified']}")
    print(f"ready_for_execution: {payload['ready_for_execution']}")
    print(f"human_review_required: {payload['human_review_required']}")
    print(f"verified: {payload['verified_count']} / {human_size(payload['verified_logical_bytes'])}")
    print(f"unique_inode_estimate: {human_size(payload['estimated_unique_inode_bytes'])}")
    print(f"blocked: {payload['blocked_count']}")
    print(f"pending_review: {payload['pending_review_count']}")
    print(f"preflight_errors: {len(payload.get('preflight_errors') or [])}")
    print("blocked_by_reason:")
    for reason, count in payload.get("blocked_by_reason", {}).items():
        print(f"- {reason}: {count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a review-only media cleanup allowlist")
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--min-age-hours", type=float, default=None, help="Defaults to the allowlist selection min age, then 72")
    parser.add_argument("--include-all-tables", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_preflight(args)
    write_json_report(args.json_report, payload)
    print_report(payload)
    return 0 if payload.get("technically_verified") else 1


if __name__ == "__main__":
    raise SystemExit(main())
