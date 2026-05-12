#!/usr/bin/env python3
"""Read-only media storage audit.

This script verifies duplicate global/user media files by hash and scans SQLite
references before any future hard-link or content-addressed migration work.
It never deletes, rewrites, or links files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_DATA_DIR = Path(os.environ.get("GAME_VIDEO_DATA_DIR", "/home/deploy/game-video-data"))
MEDIA_URL_RE = re.compile(r"/api/files/([^\s\"'<>?#)]+)")
TEXT_TYPES = ("TEXT", "CHAR", "CLOB", "VARCHAR")
DEFAULT_REFERENCE_TABLES = {
    "game_projects",
    "game_assets",
    "game_tasks",
    "viral_videos",
    "viral_analyses",
}


@dataclass(frozen=True)
class MediaPair:
    filename: str
    global_path: Path
    user_path: Path
    size: int
    same_inode: bool
    same_device: bool


@dataclass(frozen=True)
class MediaFile:
    filename: str
    path: Path
    size: int
    mtime: float
    scope: str
    user_id: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{num}B"


def file_stat(path: Path):
    try:
        return path.stat()
    except OSError:
        return None


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def write_json_report(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_duplicate_pairs(data_dir: Path) -> list[MediaPair]:
    global_dir = data_dir / "files"
    users_dir = data_dir / "users"
    global_files: dict[str, tuple[Path, int, int, int]] = {}
    if global_dir.exists():
        for path in global_dir.iterdir():
            if not path.is_file():
                continue
            st = file_stat(path)
            if st is None:
                continue
            global_files[path.name] = (path, st.st_size, st.st_ino, st.st_dev)

    pairs: list[MediaPair] = []
    if users_dir.exists():
        for user_files_dir in users_dir.glob("*/files"):
            if not user_files_dir.is_dir():
                continue
            for user_path in user_files_dir.iterdir():
                if not user_path.is_file():
                    continue
                item = global_files.get(user_path.name)
                if not item:
                    continue
                global_path, global_size, global_inode, global_device = item
                user_st = file_stat(user_path)
                if user_st is None or user_st.st_size != global_size:
                    continue
                pairs.append(MediaPair(
                    filename=user_path.name,
                    global_path=global_path,
                    user_path=user_path,
                    size=user_st.st_size,
                    same_inode=user_st.st_ino == global_inode and user_st.st_dev == global_device,
                    same_device=user_st.st_dev == global_device,
                ))
    return pairs


def list_media_files(data_dir: Path) -> list[MediaFile]:
    rows: list[MediaFile] = []
    global_dir = data_dir / "files"
    if global_dir.exists():
        for path in sorted(global_dir.iterdir()):
            if not path.is_file():
                continue
            st = file_stat(path)
            if st is None:
                continue
            rows.append(MediaFile(
                filename=path.name,
                path=path,
                size=st.st_size,
                mtime=st.st_mtime,
                scope="global",
            ))

    users_dir = data_dir / "users"
    if users_dir.exists():
        for user_files_dir in sorted(users_dir.glob("*/files")):
            if not user_files_dir.is_dir():
                continue
            user_id = user_id_from_path(user_files_dir)
            for path in sorted(user_files_dir.iterdir()):
                if not path.is_file():
                    continue
                st = file_stat(path)
                if st is None:
                    continue
                rows.append(MediaFile(
                    filename=path.name,
                    path=path,
                    size=st.st_size,
                    mtime=st.st_mtime,
                    scope="user",
                    user_id=user_id,
                ))
    return rows


def list_database_paths(data_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for name in ("game_video.db", "auth.db", "app.db"):
        path = data_dir / name
        if path.exists():
            paths.append(path)
    users_dir = data_dir / "users"
    if users_dir.exists():
        paths.extend(sorted(path for path in users_dir.glob("*/database.db") if path.is_file()))
    return paths


def connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def sql_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_names(conn: sqlite3.Connection, include_all_tables: bool) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = []
    for row in rows:
        name = row["name"]
        if name.startswith("sqlite_"):
            continue
        if include_all_tables or name in DEFAULT_REFERENCE_TABLES:
            names.append(name)
    return names


def text_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    columns = []
    for row in conn.execute(f"PRAGMA table_info({sql_ident(table)})").fetchall():
        col_type = str(row["type"] or "").upper()
        if not col_type or any(part in col_type for part in TEXT_TYPES):
            columns.append(row["name"])
    return columns


def extract_media_filenames(value: str, target_filenames: set[str] | None) -> set[str]:
    found: set[str] = set()
    for match in MEDIA_URL_RE.finditer(value or ""):
        filename = Path(match.group(1)).name
        if target_filenames is None or filename in target_filenames:
            found.add(filename)
    return found


def classify_reference_kind(table: str, column: str) -> str:
    if table == "game_projects" and column == "scenes_json":
        return "project_state"
    if table == "game_assets" and column == "image_url":
        return "asset_state"
    if table == "game_tasks":
        return "task_record"
    if table.startswith("viral_"):
        return "viral_record"
    return "other_record"


def scan_references(data_dir: Path, target_filenames: set[str], include_all_tables: bool, sample_limit: int) -> dict:
    counts: Counter[str] = Counter()
    counts_by_kind: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[dict]] = defaultdict(list)
    db_errors: list[dict] = []
    db_paths = list_database_paths(data_dir)

    for db_path in db_paths:
        try:
            conn = connect_readonly(db_path)
        except sqlite3.Error as exc:
            db_errors.append({"db": str(db_path), "error": str(exc)})
            continue
        try:
            for table in table_names(conn, include_all_tables):
                for column in text_columns(conn, table):
                    query = (
                        f"SELECT rowid AS row_id, {sql_ident(column)} AS value "
                        f"FROM {sql_ident(table)} WHERE {sql_ident(column)} LIKE ?"
                    )
                    try:
                        rows = conn.execute(query, ("%/api/files/%",)).fetchall()
                    except sqlite3.Error as exc:
                        db_errors.append({"db": str(db_path), "table": table, "column": column, "error": str(exc)})
                        continue
                    for row in rows:
                        filenames = extract_media_filenames(str(row["value"] or ""), target_filenames)
                        reference_kind = classify_reference_kind(table, column)
                        for filename in filenames:
                            counts[filename] += 1
                            counts_by_kind[filename][reference_kind] += 1
                            if len(samples[filename]) < sample_limit:
                                samples[filename].append({
                                    "db": str(db_path),
                                    "table": table,
                                    "column": column,
                                    "row_id": row["row_id"],
                                    "kind": reference_kind,
                                })
        finally:
            conn.close()

    return {
        "db_count": len(db_paths),
        "db_paths_sample": [str(path) for path in db_paths[:20]],
        "reference_counts": dict(counts),
        "reference_counts_by_kind": {filename: dict(kind_counts) for filename, kind_counts in counts_by_kind.items()},
        "reference_samples": dict(samples),
        "db_errors": db_errors,
    }


def user_id_from_path(path: Path) -> str:
    parts = path.parts
    if "users" not in parts:
        return ""
    idx = parts.index("users")
    return parts[idx + 1] if idx + 1 < len(parts) else ""


def analyze_pairs(pairs: Iterable[MediaPair], verify_hash: bool, hash_limit: int) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    hash_cache: dict[Path, str] = {}
    checked = 0
    errors: list[dict] = []

    for pair in pairs:
        global_hash = ""
        user_hash = ""
        hash_match = None
        if verify_hash and (hash_limit <= 0 or checked < hash_limit):
            try:
                global_hash = hash_cache.get(pair.global_path) or sha256_file(pair.global_path)
                hash_cache[pair.global_path] = global_hash
                user_hash = sha256_file(pair.user_path)
                hash_match = global_hash == user_hash
                checked += 1
            except OSError as exc:
                hash_match = False
                errors.append({
                    "filename": pair.filename,
                    "global_path": str(pair.global_path),
                    "user_path": str(pair.user_path),
                    "error": str(exc),
                })

        rows.append({
            "filename": pair.filename,
            "extension": pair.user_path.suffix.lower() or "[noext]",
            "size": pair.size,
            "global_path": str(pair.global_path),
            "user_path": str(pair.user_path),
            "user_id": user_id_from_path(pair.user_path),
            "same_inode": pair.same_inode,
            "same_device": pair.same_device,
            "hash_checked": bool(verify_hash and hash_match is not None),
            "sha256_match": hash_match,
            "sha256": global_hash if hash_match else "",
            "hardlink_candidate": bool(pair.same_device and not pair.same_inode and hash_match is True),
        })

    return rows, {"hash_checked_count": checked, "hash_errors": errors}


def summarize(rows: list[dict], reference_counts: dict[str, int]) -> dict:
    by_extension: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    by_user: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    hardlink_candidates = []
    already_hardlinked = 0
    hash_matches = 0
    hash_mismatches = 0
    referenced_count = 0

    for row in rows:
        ext = row["extension"]
        user_id = row["user_id"] or "[unknown]"
        by_extension[ext]["count"] += 1
        by_extension[ext]["bytes"] += int(row["size"])
        by_user[user_id]["count"] += 1
        by_user[user_id]["bytes"] += int(row["size"])
        if row["same_inode"]:
            already_hardlinked += 1
        if row["sha256_match"] is True:
            hash_matches += 1
        elif row["sha256_match"] is False:
            hash_mismatches += 1
        if reference_counts.get(row["filename"], 0) > 0:
            referenced_count += 1
        if row["hardlink_candidate"]:
            hardlink_candidates.append(row)

    return {
        "pair_count": len(rows),
        "already_hardlinked_count": already_hardlinked,
        "hash_match_count": hash_matches,
        "hash_mismatch_count": hash_mismatches,
        "referenced_filename_count": referenced_count,
        "hardlink_candidate_count": len(hardlink_candidates),
        "hardlink_candidate_bytes": sum(int(row["size"]) for row in hardlink_candidates),
        "by_extension": dict(sorted(by_extension.items())),
        "top_users": sorted(
            ({"user_id": user, **stats} for user, stats in by_user.items()),
            key=lambda row: row["bytes"],
            reverse=True,
        )[:20],
    }


def summarize_media_lifecycle(
    media_files: list[MediaFile],
    reference_counts: dict[str, int],
    reference_counts_by_kind: dict[str, dict[str, int]],
    sample_limit: int,
) -> dict:
    by_extension: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    by_scope: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    by_user: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    filename_bytes: dict[str, int] = defaultdict(int)
    filename_file_count: Counter[str] = Counter()

    for media in media_files:
        ext = media.path.suffix.lower() or "[noext]"
        by_extension[ext]["count"] += 1
        by_extension[ext]["bytes"] += media.size
        by_scope[media.scope]["count"] += 1
        by_scope[media.scope]["bytes"] += media.size
        if media.user_id:
            by_user[media.user_id]["count"] += 1
            by_user[media.user_id]["bytes"] += media.size
        filename_bytes[media.filename] += media.size
        filename_file_count[media.filename] += 1

    local_filenames = set(filename_file_count)
    referenced_filenames = {filename for filename in local_filenames if reference_counts.get(filename, 0) > 0}
    unreferenced_filenames = local_filenames - referenced_filenames

    active_state_filenames = {
        filename
        for filename in referenced_filenames
        if (
            reference_counts_by_kind.get(filename, {}).get("project_state", 0)
            + reference_counts_by_kind.get(filename, {}).get("asset_state", 0)
        ) > 0
    }
    task_record_filenames = {
        filename
        for filename in referenced_filenames
        if reference_counts_by_kind.get(filename, {}).get("task_record", 0) > 0
    }
    record_only_filenames = referenced_filenames - active_state_filenames
    task_only_filenames = task_record_filenames - active_state_filenames

    unreferenced_files = [media for media in media_files if media.filename in unreferenced_filenames]
    orphan_sample = sorted(unreferenced_files, key=lambda item: item.size, reverse=True)[:sample_limit]

    return {
        "reference_matching_scope": "filename_basename",
        "local_file_count": len(media_files),
        "local_file_bytes": sum(media.size for media in media_files),
        "local_filename_count": len(local_filenames),
        "referenced_filename_count": len(referenced_filenames),
        "unreferenced_filename_count": len(unreferenced_filenames),
        "unreferenced_file_count": len(unreferenced_files),
        "unreferenced_file_bytes": sum(media.size for media in unreferenced_files),
        "suspected_unreferenced_filename_count": len(unreferenced_filenames),
        "suspected_unreferenced_file_count": len(unreferenced_files),
        "suspected_unreferenced_file_bytes": sum(media.size for media in unreferenced_files),
        "active_state_referenced_filename_count": len(active_state_filenames),
        "record_only_referenced_filename_count": len(record_only_filenames),
        "task_only_referenced_filename_count": len(task_only_filenames),
        "reference_protected_filename_count": len(referenced_filenames),
        "duplicate_filename_count": sum(1 for count in filename_file_count.values() if count > 1),
        "by_extension": dict(sorted(by_extension.items())),
        "by_scope": dict(sorted(by_scope.items())),
        "top_users": sorted(
            ({"user_id": user, **stats} for user, stats in by_user.items()),
            key=lambda row: row["bytes"],
            reverse=True,
        )[:20],
        "largest_unreferenced_sample": [
            {
                "filename": media.filename,
                "path": str(media.path),
                "scope": media.scope,
                "user_id": media.user_id,
                "size": media.size,
                "mtime": datetime.fromtimestamp(media.mtime, timezone.utc).astimezone().replace(microsecond=0).isoformat(),
                "reference_count": int(reference_counts.get(media.filename, 0)),
            }
            for media in orphan_sample
        ],
        "pending_delete_queue": {
            "persisted": False,
            "observable_from_server": False,
            "reason": "Frontend pending deletes are in-memory until a successful save flushes them; this audit can only report persisted files and database references.",
        },
        "limitations": [
            "References are matched by /api/files/<filename> basename because the persisted URL does not carry user scope.",
            "If multiple local files share the same basename, one database reference protects that basename-level group in this report.",
            "Suspected unreferenced files are audit candidates only; cleanup must re-check current DB references and file stat before any deletion.",
        ],
        "recommendations": [
            "Do not delete unreferenced files directly from this report; run a separate dry-run cleanup plan and review samples first.",
            "Treat task-only referenced files as billing/audit records, not active project state; user-requested deletion may remove media while preserving cost records.",
            "Reference-protected filenames should remain blocked by /api/game/files/delete until active project or asset references are removed and saved.",
        ],
    }


def build_report(args: argparse.Namespace) -> dict:
    pairs = list_duplicate_pairs(args.data_dir)
    media_files = list_media_files(args.data_dir)
    target_filenames = {media.filename for media in media_files} | {pair.filename for pair in pairs}
    pair_rows, hash_report = analyze_pairs(pairs, args.verify_hash, args.hash_limit)
    reference_report = scan_references(
        args.data_dir,
        target_filenames,
        include_all_tables=args.include_all_tables,
        sample_limit=args.reference_sample_limit,
    )
    references = reference_report["reference_counts"]
    for row in pair_rows:
        row["reference_count"] = int(references.get(row["filename"], 0))
        row["reference_samples"] = reference_report["reference_samples"].get(row["filename"], [])

    summary = summarize(pair_rows, references)
    lifecycle_summary = summarize_media_lifecycle(
        media_files,
        references,
        reference_report["reference_counts_by_kind"],
        sample_limit=args.sample_limit,
    )
    sample_rows = sorted(pair_rows, key=lambda row: row["size"], reverse=True)[:args.sample_limit]
    return {
        "action": "media_audit",
        "dry_run": True,
        "created_at": now_iso(),
        "data_dir": str(args.data_dir),
        "verify_hash": args.verify_hash,
        "hash_limit": args.hash_limit,
        **summary,
        **hash_report,
        "reference_db_count": reference_report["db_count"],
        "reference_db_paths_sample": reference_report["db_paths_sample"],
        "reference_db_errors": reference_report["db_errors"],
        "reference_counts_by_kind": reference_report["reference_counts_by_kind"],
        "media_lifecycle": lifecycle_summary,
        "sample": sample_rows,
    }


def print_report(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"pairs: {payload['pair_count']}")
    print(f"hash_checked: {payload['hash_checked_count']}")
    print(f"hash_matches: {payload['hash_match_count']}")
    print(f"hash_mismatches: {payload['hash_mismatch_count']}")
    print(f"hardlink_candidates: {payload['hardlink_candidate_count']} / {human_size(payload['hardlink_candidate_bytes'])}")
    print(f"already_hardlinked: {payload['already_hardlinked_count']}")
    print(f"referenced_filenames: {payload['referenced_filename_count']}")
    lifecycle = payload.get("media_lifecycle") or {}
    print("media_lifecycle:")
    print(f"- local_files: {lifecycle.get('local_file_count', 0)} / {human_size(lifecycle.get('local_file_bytes', 0))}")
    print(f"- suspected_unreferenced_files: {lifecycle.get('suspected_unreferenced_file_count', 0)} / {human_size(lifecycle.get('suspected_unreferenced_file_bytes', 0))}")
    print(f"- active_state_referenced_filenames: {lifecycle.get('active_state_referenced_filename_count', 0)}")
    print(f"- task_only_referenced_filenames: {lifecycle.get('task_only_referenced_filename_count', 0)}")
    print("by_extension:")
    for ext, stats in payload["by_extension"].items():
        print(f"- {ext}: {stats['count']} / {human_size(stats['bytes'])}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only media duplicate and reference audit")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--no-verify-hash", dest="verify_hash", action="store_false")
    parser.set_defaults(verify_hash=True)
    parser.add_argument("--hash-limit", type=int, default=0, help="0 means verify all duplicate pairs")
    parser.add_argument("--sample-limit", type=int, default=50)
    parser.add_argument("--reference-sample-limit", type=int, default=5)
    parser.add_argument("--include-all-tables", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(args)
    write_json_report(args.json_report, payload)
    print_report(payload)
    return 0 if not payload.get("reference_db_errors") and not payload.get("hash_errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
