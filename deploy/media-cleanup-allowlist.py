#!/usr/bin/env python3
"""Build a review-only media cleanup allowlist from a dry-run plan.

This tool never deletes files. It selects a bounded subset of candidates from a
`media-cleanup-plan.py` JSON report so a human can review exact paths before any
future execution package is considered.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_MAX_BYTES = 512 * 1024 * 1024


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


def parse_bytes(value: str | int) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return 0
    lower = text.lower()
    multipliers = {
        "b": 1,
        "byte": 1,
        "bytes": 1,
        "k": 1024,
        "kb": 1024,
        "kib": 1024,
        "m": 1024 ** 2,
        "mb": 1024 ** 2,
        "mib": 1024 ** 2,
        "g": 1024 ** 3,
        "gb": 1024 ** 3,
        "gib": 1024 ** 3,
    }
    for suffix, multiplier in sorted(multipliers.items(), key=lambda item: len(item[0]), reverse=True):
        if lower.endswith(suffix):
            return int(float(lower[: -len(suffix)].strip()) * multiplier)
    return int(float(lower))


def valid_candidate(candidate: dict, min_age_hours: float, scopes: set[str]) -> tuple[bool, str]:
    if not candidate.get("candidate_id"):
        return False, "missing_candidate_id"
    if not candidate.get("path"):
        return False, "missing_path"
    if scopes and candidate.get("scope") not in scopes:
        return False, "scope_filtered"
    if int(candidate.get("reference_count") or 0) != 0:
        return False, "referenced"
    if candidate.get("reference_kinds") not in ({}, None):
        return False, "referenced"
    recheck = candidate.get("recheck") or {}
    if recheck.get("reference_class") != "unreferenced":
        return False, "not_unreferenced"
    if recheck.get("path_exists") is not True:
        return False, "path_not_confirmed"
    if recheck.get("regular_file") is not True:
        return False, "not_regular_file"
    if recheck.get("symlink") is True:
        return False, "symlink"
    if recheck.get("allowed_scope") is not True:
        return False, "outside_media_scope"
    if float(candidate.get("age_hours") or 0) < min_age_hours:
        return False, "too_recent"
    if int(candidate.get("size") or 0) <= 0:
        return False, "empty_or_invalid_size"
    return True, ""


def sort_candidates(candidates: list[dict], sort_mode: str) -> list[dict]:
    if sort_mode == "oldest":
        return sorted(candidates, key=lambda row: (-float(row.get("age_hours") or 0), -int(row.get("size") or 0), row.get("path") or ""))
    if sort_mode == "size-asc":
        return sorted(candidates, key=lambda row: (int(row.get("size") or 0), row.get("path") or ""))
    return sorted(candidates, key=lambda row: (-int(row.get("size") or 0), -float(row.get("age_hours") or 0), row.get("path") or ""))


def build_allowlist(args: argparse.Namespace) -> dict:
    plan = load_json(args.plan)
    preflight_errors: list[str] = []
    if plan.get("action") != "media_cleanup_plan":
        preflight_errors.append("plan_action_must_be_media_cleanup_plan")
    if plan.get("dry_run") is not True:
        preflight_errors.append("plan_must_be_dry_run")
    if plan.get("deletion_enabled") is not False:
        preflight_errors.append("plan_deletion_must_be_disabled")
    if plan.get("reference_db_errors"):
        preflight_errors.append("plan_has_reference_db_errors")

    max_bytes = parse_bytes(args.max_bytes)
    scopes = {scope.strip() for scope in args.scope.split(",") if scope.strip()}
    rejected: dict[str, int] = {}
    accepted: list[dict] = []

    for candidate in plan.get("candidates") or []:
        ok, reason = valid_candidate(candidate, min_age_hours=args.min_age_hours, scopes=scopes)
        if not ok:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        accepted.append(candidate)

    selected: list[dict] = []
    selected_bytes = 0
    max_count = max(0, args.max_count)
    for candidate in sort_candidates(accepted, args.sort):
        size = int(candidate.get("size") or 0)
        if max_count and len(selected) >= max_count:
            rejected["max_count_reached"] = rejected.get("max_count_reached", 0) + 1
            continue
        if max_bytes and selected_bytes + size > max_bytes:
            rejected["max_bytes_reached"] = rejected.get("max_bytes_reached", 0) + 1
            if not args.fill_gaps:
                break
            continue
        selected.append({
            "candidate_id": candidate["candidate_id"],
            "path": candidate["path"],
            "filename": candidate.get("filename", ""),
            "scope": candidate.get("scope", ""),
            "user_id": candidate.get("user_id", ""),
            "size": size,
            "mtime": candidate.get("mtime", ""),
            "age_hours": candidate.get("age_hours", 0),
            "reference_count": int(candidate.get("reference_count") or 0),
            "reference_kinds": candidate.get("reference_kinds") or {},
            "expected": {
                "size": size,
                "mtime": candidate.get("mtime", ""),
                "reference_class": "unreferenced",
                "path": candidate["path"],
            },
            "review_status": "pending",
        })
        selected_bytes += size

    return {
        "action": "media_cleanup_allowlist",
        "dry_run": True,
        "deletion_enabled": False,
        "review_required": True,
        "created_at": now_iso(),
        "source_plan": str(args.plan),
        "source_plan_created_at": plan.get("created_at", ""),
        "source_candidate_count": int(plan.get("candidate_count") or 0),
        "source_estimated_reclaim_bytes": int(plan.get("estimated_reclaim_bytes") or 0),
        "selection": {
            "sort": args.sort,
            "max_count": max_count,
            "max_bytes": max_bytes,
            "min_age_hours": args.min_age_hours,
            "fill_gaps": args.fill_gaps,
            "scope": sorted(scopes) if scopes else ["global", "user"],
        },
        "preflight_errors": preflight_errors,
        "selected_count": len(selected),
        "selected_logical_bytes": selected_bytes,
        "allowlist": selected,
        "rejected_by_reason": dict(sorted(rejected.items())),
        "instructions": [
            "Human review must mark exact candidate_ids as approved before any future execution package.",
            "A future execution tool must re-run media-cleanup-plan.py and verify candidate_id, path, size, mtime, reference_count, reference_kinds, and allowed scope.",
            "Do not edit this file into an execute command; this allowlist is only an approval artifact.",
        ],
    }


def print_report(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"dry_run: {payload['dry_run']} deletion_enabled: {payload['deletion_enabled']} review_required: {payload['review_required']}")
    print(f"selected: {payload['selected_count']} / {human_size(payload['selected_logical_bytes'])}")
    print(f"preflight_errors: {len(payload.get('preflight_errors') or [])}")
    print("rejected_by_reason:")
    for reason, count in payload.get("rejected_by_reason", {}).items():
        print(f"- {reason}: {count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a review-only media cleanup allowlist")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--max-count", type=int, default=30)
    parser.add_argument("--max-bytes", default=str(DEFAULT_MAX_BYTES), help="Bytes or suffix like 512MiB, 1GiB")
    parser.add_argument("--min-age-hours", type=float, default=72.0)
    parser.add_argument("--scope", default="global,user", help="Comma separated scopes: global,user")
    parser.add_argument("--sort", choices=("size-desc", "size-asc", "oldest"), default="size-desc")
    parser.add_argument("--fill-gaps", action="store_true", help="Keep scanning smaller candidates after max-bytes is reached")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_allowlist(args)
    write_json_report(args.json_report, payload)
    print_report(payload)
    return 0 if not payload.get("preflight_errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
