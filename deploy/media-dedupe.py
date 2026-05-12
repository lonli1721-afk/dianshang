#!/usr/bin/env python3
"""Hard-link duplicate global/user media files after strict verification.

Default mode is dry-run. Execution replaces only the user-scoped duplicate file
with a hard link to the existing global file, keeping both paths and URLs valid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DATA_DIR = Path(os.environ.get("GAME_VIDEO_DATA_DIR", "/home/deploy/game-video-data"))


@dataclass(frozen=True)
class MediaPair:
    filename: str
    global_path: Path
    user_path: Path
    size: int
    global_inode: int
    user_inode: int
    global_device: int
    user_device: int


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
                global_item = global_files.get(user_path.name)
                if not global_item:
                    continue
                global_path, global_size, global_inode, global_device = global_item
                user_st = file_stat(user_path)
                if user_st is None or user_st.st_size != global_size:
                    continue
                pairs.append(MediaPair(
                    filename=user_path.name,
                    global_path=global_path,
                    user_path=user_path,
                    size=user_st.st_size,
                    global_inode=global_inode,
                    user_inode=user_st.st_ino,
                    global_device=global_device,
                    user_device=user_st.st_dev,
                ))
    return pairs


def user_id_from_path(path: Path) -> str:
    parts = path.parts
    if "users" not in parts:
        return ""
    idx = parts.index("users")
    return parts[idx + 1] if idx + 1 < len(parts) else ""


def candidate_reason(pair: MediaPair) -> str:
    if pair.global_device != pair.user_device:
        return "different_device"
    if pair.global_inode == pair.user_inode:
        return "already_hardlinked"
    return ""


def verify_pair(pair: MediaPair) -> tuple[bool, str, str]:
    global_st = file_stat(pair.global_path)
    user_st = file_stat(pair.user_path)
    if global_st is None:
        return False, "global_missing", ""
    if user_st is None:
        return False, "user_missing", ""
    if not pair.global_path.is_file() or not pair.user_path.is_file():
        return False, "not_regular_file", ""
    if global_st.st_dev != user_st.st_dev:
        return False, "different_device", ""
    if global_st.st_ino == user_st.st_ino:
        return False, "already_hardlinked", ""
    if global_st.st_size != user_st.st_size:
        return False, "size_changed", ""
    digest = sha256_file(pair.global_path)
    user_digest = sha256_file(pair.user_path)
    if digest != user_digest:
        return False, "sha256_mismatch", ""
    return True, "ok", digest


def make_hardlink(pair: MediaPair) -> None:
    tmp = pair.user_path.with_name(f".{pair.user_path.name}.dedupe-{os.getpid()}.tmp")
    try:
        if tmp.exists():
            tmp.unlink()
        os.link(pair.global_path, tmp)
        tmp_st = tmp.stat()
        global_st = pair.global_path.stat()
        if tmp_st.st_ino != global_st.st_ino or tmp_st.st_dev != global_st.st_dev:
            raise RuntimeError("temporary hard link did not point to global file")
        os.replace(tmp, pair.user_path)
        final_st = pair.user_path.stat()
        if final_st.st_ino != global_st.st_ino or final_st.st_dev != global_st.st_dev:
            raise RuntimeError("final user path is not linked to global file")
    finally:
        if tmp.exists():
            tmp.unlink()


def summarize(rows: list[dict]) -> dict:
    by_extension: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    by_user: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    for row in rows:
        if not row.get("candidate"):
            continue
        ext = row["extension"]
        user_id = row["user_id"] or "[unknown]"
        by_extension[ext]["count"] += 1
        by_extension[ext]["bytes"] += int(row["size"])
        by_user[user_id]["count"] += 1
        by_user[user_id]["bytes"] += int(row["size"])
    return {
        "by_extension": dict(sorted(by_extension.items())),
        "top_users": sorted(
            ({"user_id": user, **stats} for user, stats in by_user.items()),
            key=lambda item: item["bytes"],
            reverse=True,
        )[:20],
    }


def build_report(args: argparse.Namespace) -> dict:
    pairs = list_duplicate_pairs(args.data_dir)
    rows: list[dict] = []
    skipped: list[dict] = []
    executed: list[dict] = []
    errors: list[dict] = []
    candidate_bytes = 0
    verified_count = 0

    for pair in pairs:
        base = {
            "filename": pair.filename,
            "extension": pair.user_path.suffix.lower() or "[noext]",
            "size": pair.size,
            "global_path": str(pair.global_path),
            "user_path": str(pair.user_path),
            "user_id": user_id_from_path(pair.user_path),
        }
        reason = candidate_reason(pair)
        if reason:
            row = {**base, "candidate": False, "reason": reason}
            rows.append(row)
            skipped.append(row)
            continue

        ok, verify_reason, digest = verify_pair(pair)
        if not ok:
            row = {**base, "candidate": False, "reason": verify_reason}
            rows.append(row)
            skipped.append(row)
            continue

        verified_count += 1
        candidate_bytes += pair.size
        row = {
            **base,
            "candidate": True,
            "reason": "ok",
            "sha256": digest,
            "executed": False,
        }
        rows.append(row)

        if args.execute:
            try:
                make_hardlink(pair)
                row["executed"] = True
                executed.append(row)
            except Exception as exc:  # noqa: BLE001 - report all file operation failures.
                error = {**base, "error": str(exc)}
                errors.append(error)

    summary = summarize(rows)
    return {
        "action": "media_dedupe",
        "dry_run": not args.execute,
        "created_at": now_iso(),
        "data_dir": str(args.data_dir),
        "total_duplicate_pairs": len(pairs),
        "verified_candidate_count": verified_count,
        "candidate_bytes": candidate_bytes,
        "executed_count": len(executed),
        "executed_bytes": sum(int(row["size"]) for row in executed),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "errors": errors,
        "sample": rows[:args.sample_limit],
        "executed_sample": executed[:args.sample_limit],
        "skipped_sample": skipped[:args.sample_limit],
        **summary,
    }


def print_report(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"dry_run: {payload['dry_run']}")
    print(f"duplicate_pairs: {payload['total_duplicate_pairs']}")
    print(f"verified_candidates: {payload['verified_candidate_count']} / {human_size(payload['candidate_bytes'])}")
    print(f"executed: {payload['executed_count']} / {human_size(payload['executed_bytes'])}")
    print(f"skipped: {payload['skipped_count']}")
    print(f"errors: {payload['error_count']}")
    print("by_extension:")
    for ext, stats in payload["by_extension"].items():
        print(f"- {ext}: {stats['count']} / {human_size(stats['bytes'])}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run or execute hard-link dedupe for verified duplicate media")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--sample-limit", type=int, default=50)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(args)
    write_json_report(args.json_report, payload)
    print_report(payload)
    return 0 if payload["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
