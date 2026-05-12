#!/usr/bin/env python3
"""Storage lifecycle tooling for production disk governance.

Default behavior is read-only. Destructive actions require --execute.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DATA_DIR = Path(os.environ.get("GAME_VIDEO_DATA_DIR", "/home/deploy/game-video-data"))
DEFAULT_BACKUP_DIR = Path(os.environ.get("GAME_VIDEO_BACKUP_DIR", "/home/deploy/game-video-backups"))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
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


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{num}B"


def disk_report(paths: list[Path]) -> list[dict]:
    seen: set[Path] = set()
    rows = []
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


def write_json_report(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_full_backups(backup_dir: Path) -> list[Path]:
    return sorted(
        backup_dir.glob("game-video-data-*.tar.gz"),
        key=lambda item: item.stat().st_mtime if item.exists() else 0,
        reverse=True,
    )


def cleanup_full_backups(args: argparse.Namespace) -> dict:
    backup_dir = args.backup_dir
    backups = list_full_backups(backup_dir)
    keep_count = max(0, args.keep_count)
    keep = backups[:keep_count]
    candidates = backups[keep_count:]
    candidate_bytes = sum(file_size(path) for path in candidates)
    deleted: list[str] = []
    errors: list[dict] = []
    if args.execute:
        for path in candidates:
            try:
                path.unlink()
                deleted.append(str(path))
            except OSError as exc:
                errors.append({"path": str(path), "error": str(exc)})
    return {
        "action": "cleanup_full_backups",
        "dry_run": not args.execute,
        "backup_dir": str(backup_dir),
        "keep_count": keep_count,
        "total_count": len(backups),
        "keep": [str(path) for path in keep],
        "candidate_count": len(candidates),
        "candidate_bytes": candidate_bytes,
        "candidates": [str(path) for path in candidates],
        "deleted_count": len(deleted),
        "deleted": deleted,
        "errors": errors,
        "created_at": now_iso(),
    }


def list_cloud_dbs(data_dir: Path) -> list[Path]:
    root = data_dir / "cloud-dbs"
    return sorted(
        [path for path in root.glob("*.db") if path.is_file()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )


def cleanup_cloud_dbs(args: argparse.Namespace) -> dict:
    files = list_cloud_dbs(args.data_dir)
    keep_count = max(0, args.keep_count)
    keep = files[:keep_count]
    candidates = files[keep_count:]
    candidate_bytes = sum(file_size(path) for path in candidates)
    deleted: list[str] = []
    errors: list[dict] = []
    if args.execute:
        for path in candidates:
            try:
                path.unlink()
                deleted.append(str(path))
            except OSError as exc:
                errors.append({"path": str(path), "error": str(exc)})
    return {
        "action": "cleanup_cloud_dbs",
        "dry_run": not args.execute,
        "data_dir": str(args.data_dir),
        "keep_count": keep_count,
        "total_count": len(files),
        "keep_sample": [str(path) for path in keep[:10]],
        "candidate_count": len(candidates),
        "candidate_bytes": candidate_bytes,
        "candidate_sample": [str(path) for path in candidates[:50]],
        "deleted_count": len(deleted),
        "deleted": deleted,
        "errors": errors,
        "created_at": now_iso(),
    }


@dataclass(frozen=True)
class DuplicatePair:
    filename: str
    global_path: Path
    user_path: Path
    size: int
    same_inode: bool


def duplicate_pairs(data_dir: Path) -> list[DuplicatePair]:
    global_files_dir = data_dir / "files"
    users_dir = data_dir / "users"
    global_files: dict[str, tuple[Path, int, int, int]] = {}
    if global_files_dir.exists():
        for path in global_files_dir.iterdir():
            if not path.is_file():
                continue
            st = path.stat()
            global_files[path.name] = (path, st.st_size, st.st_ino, st.st_dev)

    pairs: list[DuplicatePair] = []
    if users_dir.exists():
        for user_files_dir in users_dir.glob("*/files"):
            for path in user_files_dir.iterdir():
                if not path.is_file() or path.name not in global_files:
                    continue
                global_path, global_size, global_inode, global_device = global_files[path.name]
                st = path.stat()
                if st.st_size != global_size:
                    continue
                pairs.append(DuplicatePair(
                    filename=path.name,
                    global_path=global_path,
                    user_path=path,
                    size=st.st_size,
                    same_inode=st.st_ino == global_inode and st.st_dev == global_device,
                ))
    return pairs


def duplicate_report(args: argparse.Namespace) -> dict:
    pairs = duplicate_pairs(args.data_dir)
    reclaimable = [pair for pair in pairs if not pair.same_inode]
    by_ext: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    for pair in reclaimable:
        ext = pair.user_path.suffix.lower() or "[noext]"
        by_ext[ext]["count"] += 1
        by_ext[ext]["bytes"] += pair.size
    return {
        "action": "duplicate_files_report",
        "dry_run": True,
        "data_dir": str(args.data_dir),
        "duplicate_pair_count": len(pairs),
        "already_hardlinked_count": len([pair for pair in pairs if pair.same_inode]),
        "reclaimable_pair_count": len(reclaimable),
        "potential_reclaim_bytes": sum(pair.size for pair in reclaimable),
        "by_extension": by_ext,
        "sample": [
            {
                "filename": pair.filename,
                "size": pair.size,
                "global_path": str(pair.global_path),
                "user_path": str(pair.user_path),
            }
            for pair in reclaimable[:50]
        ],
        "created_at": now_iso(),
    }


def summary(args: argparse.Namespace) -> dict:
    data_dir = args.data_dir
    backup_dir = args.backup_dir
    full_backups = list_full_backups(backup_dir)
    cloud_dbs = list_cloud_dbs(data_dir)
    dupes = duplicate_pairs(data_dir)
    reclaimable_dupes = [pair for pair in dupes if not pair.same_inode]
    paths = {
        "data": data_dir,
        "backups": backup_dir,
        "users": data_dir / "users",
        "global_files": data_dir / "files",
        "cloud_dbs": data_dir / "cloud-dbs",
        "auto_db_backups": data_dir / "backups" / "auto",
    }
    sizes = {name: dir_size(path) for name, path in paths.items()}
    unique_sizes = {name: unique_dir_size(path) for name, path in paths.items()}
    return {
        "action": "summary",
        "created_at": now_iso(),
        "disk": disk_report([data_dir, backup_dir]),
        "sizes": sizes,
        "unique_sizes": unique_sizes,
        "hardlink_savings_bytes": max(0, sizes["data"] - unique_sizes["data"]),
        "full_backup_count": len(full_backups),
        "full_backup_bytes": sum(file_size(path) for path in full_backups),
        "latest_full_backup": str(full_backups[0]) if full_backups else "",
        "cloud_dbs_count": len(cloud_dbs),
        "cloud_dbs_bytes": sum(file_size(path) for path in cloud_dbs),
        "duplicate_pair_count": len(dupes),
        "duplicate_potential_reclaim_bytes": sum(pair.size for pair in reclaimable_dupes),
    }


def print_human(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if "candidate_bytes" in payload:
        print(f"candidate_reclaim: {human_size(int(payload['candidate_bytes']))}")
    if "potential_reclaim_bytes" in payload:
        print(f"potential_reclaim: {human_size(int(payload['potential_reclaim_bytes']))}")
    if payload.get("action") == "summary":
        unique_sizes = payload.get("unique_sizes", {})
        for name, size in payload.get("sizes", {}).items():
            unique = unique_sizes.get(name)
            if unique is None:
                print(f"{name}: {human_size(int(size))}")
            else:
                print(f"{name}: logical {human_size(int(size))}, unique {human_size(int(unique))}")
        print(f"hardlink_savings: {human_size(int(payload.get('hardlink_savings_bytes', 0)))}")
        print(f"full_backups: {payload.get('full_backup_count')} / {human_size(int(payload.get('full_backup_bytes', 0)))}")
        print(f"cloud_dbs: {payload.get('cloud_dbs_count')} / {human_size(int(payload.get('cloud_dbs_bytes', 0)))}")
        print(f"duplicate_potential: {human_size(int(payload.get('duplicate_potential_reclaim_bytes', 0)))}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Game video storage lifecycle governance")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--json-report", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("summary", help="Read-only disk and lifecycle summary")

    p_full = sub.add_parser("cleanup-full-backups", help="Keep newest full data backups; delete older ones only with --execute")
    p_full.add_argument("--keep-count", type=int, default=1)
    p_full.add_argument("--execute", action="store_true")

    p_cloud = sub.add_parser("cleanup-cloud-dbs", help="Keep newest cloud-dbs snapshots; delete older ones only with --execute")
    p_cloud.add_argument("--keep-count", type=int, default=200)
    p_cloud.add_argument("--execute", action="store_true")

    sub.add_parser("duplicate-files-report", help="Read-only duplicate global/user file report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "summary":
        payload = summary(args)
    elif args.command == "cleanup-full-backups":
        payload = cleanup_full_backups(args)
    elif args.command == "cleanup-cloud-dbs":
        payload = cleanup_cloud_dbs(args)
    elif args.command == "duplicate-files-report":
        payload = duplicate_report(args)
    else:
        parser.error(f"unknown command: {args.command}")
        return 2
    write_json_report(args.json_report, payload)
    print_human(payload)
    return 0 if not payload.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
