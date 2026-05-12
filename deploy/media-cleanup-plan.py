#!/usr/bin/env python3
"""Build a read-only media cleanup plan.

This script does not delete files. It re-scans current media files and database
references, then emits a conservative dry-run candidate list for later manual
review. Any future deletion tool must re-check DB references and file stat
again before unlinking.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DATA_DIR = Path(os.environ.get("GAME_VIDEO_DATA_DIR", "/home/deploy/game-video-data"))


def load_media_audit_module():
    path = Path(__file__).with_name("media-audit.py")
    spec = importlib.util.spec_from_file_location("media_audit_for_cleanup_plan", path)
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


def write_json_report(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stable_candidate_id(path: Path, size: int, mtime: float) -> str:
    raw = f"{path}\n{size}\n{mtime:.6f}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def path_scope(path: Path, data_dir: Path) -> tuple[str, str, bool]:
    resolved = path.resolve()
    data_root = data_dir.resolve()
    global_files = (data_root / "files").resolve()
    users_root = (data_root / "users").resolve()
    try:
        resolved.relative_to(global_files)
        return "global", "", True
    except ValueError:
        pass

    try:
        relative = resolved.relative_to(users_root)
    except ValueError:
        return "", "", False
    parts = relative.parts
    if len(parts) >= 3 and parts[1] == "files":
        return "user", parts[0], True
    return "", "", False


def reference_kind_counts(reference_counts_by_kind: dict[str, dict[str, int]], filename: str) -> dict[str, int]:
    return {key: int(value) for key, value in (reference_counts_by_kind.get(filename) or {}).items()}


def classify_reference(kind_counts: dict[str, int]) -> str:
    active_count = kind_counts.get("project_state", 0) + kind_counts.get("asset_state", 0)
    total = sum(kind_counts.values())
    if active_count:
        return "active_state_reference"
    if kind_counts.get("task_record", 0) and total == kind_counts.get("task_record", 0):
        return "task_only_reference"
    if total:
        return "record_only_reference"
    return "unreferenced"


def estimate_reclaim_bytes(all_media: list, candidate_paths: set[str]) -> int:
    groups: dict[tuple[int, int], list[tuple[str, int]]] = defaultdict(list)
    for media in all_media:
        try:
            stat = media.path.stat()
        except OSError:
            continue
        groups[(stat.st_dev, stat.st_ino)].append((str(media.path), stat.st_size))

    total = 0
    for paths in groups.values():
        group_paths = {path for path, _size in paths}
        if group_paths and group_paths.issubset(candidate_paths):
            total += max(size for _path, size in paths)
    return total


def build_plan(args: argparse.Namespace) -> dict:
    media_audit = load_media_audit_module()
    data_dir = args.data_dir
    media_files = media_audit.list_media_files(data_dir)
    filenames = {media.filename for media in media_files}
    reference_report = media_audit.scan_references(
        data_dir,
        filenames,
        include_all_tables=args.include_all_tables,
        sample_limit=args.reference_sample_limit,
    )
    reference_counts = reference_report["reference_counts"]
    reference_counts_by_kind = reference_report["reference_counts_by_kind"]

    now_ts = datetime.now(timezone.utc).timestamp()
    candidates: list[dict] = []
    skipped_by_reason: Counter[str] = Counter()
    skipped_sample: list[dict] = []
    candidate_paths: set[str] = set()

    for media in media_files:
        path = media.path
        scope, user_id, allowed_scope = path_scope(path, data_dir)
        try:
            stat = path.lstat()
        except OSError as exc:
            reason = "stat_failed"
            skipped_by_reason[reason] += 1
            if len(skipped_sample) < args.sample_limit:
                skipped_sample.append({"path": str(path), "reason": reason, "error": str(exc)})
            continue

        if not allowed_scope:
            reason = "outside_media_scope"
        elif path.is_symlink():
            reason = "symlink"
        elif not path.is_file():
            reason = "not_regular_file"
        else:
            kind_counts = reference_kind_counts(reference_counts_by_kind, media.filename)
            reference_class = classify_reference(kind_counts)
            age_hours = max(0.0, (now_ts - stat.st_mtime) / 3600)
            if reference_class != "unreferenced":
                reason = reference_class
            elif age_hours < args.min_age_hours:
                reason = "too_recent"
            else:
                reason = ""

        if reason:
            skipped_by_reason[reason] += 1
            if len(skipped_sample) < args.sample_limit:
                skipped_sample.append({
                    "filename": media.filename,
                    "path": str(path),
                    "scope": scope or media.scope,
                    "user_id": user_id or media.user_id,
                    "size": int(stat.st_size),
                    "reason": reason,
                    "reference_count": int(reference_counts.get(media.filename, 0)),
                    "reference_kinds": reference_kind_counts(reference_counts_by_kind, media.filename),
                })
            continue

        candidate = {
            "candidate_id": stable_candidate_id(path, int(stat.st_size), float(stat.st_mtime)),
            "filename": media.filename,
            "path": str(path),
            "scope": scope or media.scope,
            "user_id": user_id or media.user_id,
            "size": int(stat.st_size),
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone().replace(microsecond=0).isoformat(),
            "age_hours": round(max(0.0, (now_ts - stat.st_mtime) / 3600), 2),
            "reference_count": int(reference_counts.get(media.filename, 0)),
            "reference_kinds": reference_kind_counts(reference_counts_by_kind, media.filename),
            "recheck": {
                "path_exists": True,
                "regular_file": True,
                "symlink": False,
                "allowed_scope": True,
                "reference_class": "unreferenced",
                "min_age_hours": args.min_age_hours,
            },
        }
        candidates.append(candidate)
        candidate_paths.add(str(path))

    candidate_logical_bytes = sum(int(row["size"]) for row in candidates)
    estimated_reclaim_bytes = estimate_reclaim_bytes(media_files, candidate_paths)
    candidate_limit = max(0, args.candidate_limit)
    limited_candidates = candidates if candidate_limit == 0 else candidates[:candidate_limit]

    return {
        "action": "media_cleanup_plan",
        "dry_run": True,
        "deletion_enabled": False,
        "created_at": now_iso(),
        "data_dir": str(data_dir),
        "reference_matching_scope": "filename_basename",
        "min_age_hours": args.min_age_hours,
        "include_all_tables": args.include_all_tables,
        "local_file_count": len(media_files),
        "local_filename_count": len(filenames),
        "candidate_count": len(candidates),
        "candidate_logical_bytes": candidate_logical_bytes,
        "estimated_reclaim_bytes": estimated_reclaim_bytes,
        "candidate_limit": candidate_limit,
        "candidates_returned": len(limited_candidates),
        "candidates": limited_candidates,
        "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
        "skipped_sample": skipped_sample,
        "reference_db_count": reference_report["db_count"],
        "reference_db_errors": reference_report["db_errors"],
        "limitations": [
            "This is a dry-run plan and cannot delete files.",
            "References are matched by /api/files/<filename> basename because persisted URLs do not carry user scope.",
            "Estimated reclaim bytes count hard-linked inode groups once and only when every path in that inode group is a candidate.",
            "Any future deletion step must re-check current DB references, path scope, symlink status, size, mtime, and inode before unlinking.",
        ],
    }


def print_report(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"dry_run: {payload['dry_run']} deletion_enabled: {payload['deletion_enabled']}")
    print(f"local_files: {payload['local_file_count']}")
    print(f"candidates: {payload['candidate_count']} / {human_size(payload['candidate_logical_bytes'])}")
    print(f"estimated_reclaim: {human_size(payload['estimated_reclaim_bytes'])}")
    print(f"reference_db_errors: {len(payload.get('reference_db_errors') or [])}")
    print("skipped_by_reason:")
    for reason, count in payload.get("skipped_by_reason", {}).items():
        print(f"- {reason}: {count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a read-only media cleanup plan")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--min-age-hours", type=float, default=24.0)
    parser.add_argument("--candidate-limit", type=int, default=1000, help="0 means include all candidates in JSON output")
    parser.add_argument("--sample-limit", type=int, default=50)
    parser.add_argument("--reference-sample-limit", type=int, default=3)
    parser.add_argument("--include-all-tables", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_plan(args)
    write_json_report(args.json_report, payload)
    print_report(payload)
    return 0 if not payload.get("reference_db_errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
