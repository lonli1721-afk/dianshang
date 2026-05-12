#!/usr/bin/env python3
"""Blue/green release helper for Game Video Tool.

The script is intentionally conservative:
- it never edits nginx or systemd files directly;
- mutating steps require --execute;
- cutover is delegated to the root-owned switch script configured in sudoers.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.request import urlopen


ALLOWED_PORTS = (57991, 57992)
RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")
DEFAULT_APP_DIR = Path("/home/deploy/game-video-tool")
DEFAULT_RUNTIME_DIR = Path("/home/deploy/game-video-runtime")
DEFAULT_BACKUP_DIR = Path("/home/deploy/game-video-backups")
DEFAULT_SWITCH_COMMAND = Path("/usr/local/sbin/game-video-switch-upstream")
REQUIRED_MEMBERS = (
    "game-video-tool/server/main.py",
    "game-video-tool/react-ui/dist/index.html",
)
BANNED_PARTS = {
    ".git",
    ".env",
    ".local-data",
    ".venv",
    "node_modules",
    "__pycache__",
}


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class PackageInspection:
    ok: bool
    errors: list[str]
    member_count: int
    required_found: list[str]


def fail(message: str) -> None:
    print("FAILED")
    print(f"reason: {message}")
    raise SystemExit(1)


def validate_port(port: int) -> int:
    if port not in ALLOWED_PORTS:
        raise ReleaseError(f"unsupported port {port}; allowed ports are {ALLOWED_PORTS}")
    return port


def validate_release_id(release_id: str) -> str:
    if not RELEASE_ID_RE.fullmatch(release_id):
        raise ReleaseError(
            "invalid release id; use 3-80 chars from letters, numbers, dot, underscore, and dash, "
            "and start with a letter or number"
        )
    return release_id


def other_port(port: int) -> int:
    validate_port(port)
    return ALLOWED_PORTS[1] if port == ALLOWED_PORTS[0] else ALLOWED_PORTS[0]


def read_active_port(runtime_dir: Path) -> int:
    path = runtime_dir / "active-port"
    if not path.exists():
        return ALLOWED_PORTS[0]
    raw = path.read_text(encoding="utf-8").strip()
    try:
        return validate_port(int(raw))
    except (ValueError, ReleaseError) as exc:
        raise ReleaseError(f"invalid active port file {path}: {raw}") from exc


def _member_has_banned_part(name: str) -> bool:
    parts = [part for part in Path(name).parts if part not in ("", ".")]
    return any(part in BANNED_PARTS or part.startswith("._") for part in parts)


def inspect_package(package_path: Path) -> PackageInspection:
    errors: list[str] = []
    required = set(REQUIRED_MEMBERS)
    found: set[str] = set()
    count = 0

    if not package_path.exists():
        return PackageInspection(False, [f"package not found: {package_path}"], 0, [])
    if not tarfile.is_tarfile(package_path):
        return PackageInspection(False, [f"not a tar archive: {package_path}"], 0, [])

    with tarfile.open(package_path, "r:*") as tar:
        for member in tar.getmembers():
            count += 1
            name = member.name
            if name in required:
                found.add(name)
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                errors.append(f"unsafe member path: {member.name}")
            if _member_has_banned_part(member.name):
                errors.append(f"banned member in package: {member.name}")
            if not (member.isfile() or member.isdir()):
                errors.append(f"unsupported tar member type: {member.name}")

    for member in sorted(required - found):
        errors.append(f"required member missing: {member}")

    return PackageInspection(not errors, errors, count, sorted(found))


def extract_checked_package(package_path: Path, target_root: Path) -> PackageInspection:
    inspection = inspect_package(package_path)
    if not inspection.ok:
        raise ReleaseError("; ".join(inspection.errors))
    with tarfile.open(package_path, "r:*") as tar:
        tar.extractall(target_root)
    return inspection


def run_command(command: list[str], *, timeout: int = 60, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def health_ok(port: int, *, timeout_seconds: float = 3.0) -> bool:
    validate_port(port)
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout_seconds) as response:
            return response.status == 200
    except Exception:
        return False


def wait_for_health(port: int, *, timeout_seconds: int = 45) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if health_ok(port):
            return
        time.sleep(1)
    raise ReleaseError(f"backend on port {port} did not become healthy within {timeout_seconds}s")


def release_root(runtime_dir: Path, release_id: str) -> Path:
    return runtime_dir / "releases" / validate_release_id(release_id)


def slot_current(runtime_dir: Path, port: int) -> Path:
    validate_port(port)
    return runtime_dir / "slots" / str(port) / "current"


def preserve_frontend_assets(release_dir: Path, source_dist: Path) -> dict:
    target_assets = release_dir / "react-ui" / "dist" / "assets"
    source_assets = source_dist / "assets"
    report = {
        "source_dist": str(source_dist),
        "target_assets": str(target_assets),
        "source_exists": source_assets.exists(),
        "preserved_count": 0,
    }
    if not source_assets.exists() or not target_assets.exists():
        return report
    for asset in sorted(source_assets.iterdir()):
        if not asset.is_file() or asset.suffix not in {".js", ".css"}:
            continue
        target = target_assets / asset.name
        if target.exists():
            continue
        shutil.copy2(asset, target)
        report["preserved_count"] += 1
    return report


def prepare_release(
    package_path: Path,
    runtime_dir: Path,
    release_id: str,
    *,
    execute: bool,
    preserve_assets_from: Path | None = None,
) -> dict:
    release_id = validate_release_id(release_id)
    inspection = inspect_package(package_path)
    if not inspection.ok:
        raise ReleaseError("; ".join(inspection.errors))

    target_root = release_root(runtime_dir, release_id)
    release_dir = target_root / "game-video-tool"
    report = {
        "release_id": release_id,
        "package": str(package_path),
        "runtime_dir": str(runtime_dir),
        "release_dir": str(release_dir),
        "execute": execute,
        "package_member_count": inspection.member_count,
    }
    if not execute:
        return report

    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)
    extract_checked_package(package_path, target_root)
    source_dist = preserve_assets_from or (DEFAULT_APP_DIR / "react-ui" / "dist")
    report["frontend_asset_preservation"] = preserve_frontend_assets(release_dir, source_dist)
    result = run_command([sys.executable, "-m", "compileall", "server"], cwd=release_dir, timeout=120)
    if result.returncode != 0:
        raise ReleaseError(f"compileall failed:\n{result.stdout}")
    report["compileall"] = "ok"
    return report


def point_slot(runtime_dir: Path, port: int, release_id: str, *, execute: bool) -> dict:
    validate_port(port)
    release_id = validate_release_id(release_id)
    target = release_root(runtime_dir, release_id) / "game-video-tool"
    current = slot_current(runtime_dir, port)
    report = {
        "port": port,
        "release_id": release_id,
        "target": str(target),
        "slot_current": str(current),
        "execute": execute,
    }
    if not execute:
        return report
    if not target.exists():
        raise ReleaseError(f"release directory not found: {target}")
    current.parent.mkdir(parents=True, exist_ok=True)
    tmp_link = current.with_name(f".current-{release_id}.tmp")
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    tmp_link.symlink_to(target)
    tmp_link.replace(current)
    return report


def start_service(port: int, *, execute: bool, timeout_seconds: int) -> dict:
    validate_port(port)
    command = ["sudo", "-n", "/usr/bin/systemctl", "restart", f"game-video-tool@{port}.service"]
    report = {"port": port, "command": command, "execute": execute}
    if not execute:
        return report
    result = run_command(command, timeout=60)
    if result.returncode != 0:
        raise ReleaseError(f"failed to start standby service:\n{result.stdout}")
    wait_for_health(port, timeout_seconds=timeout_seconds)
    report["health"] = "ok"
    return report


def cutover(port: int, switch_command: Path, *, execute: bool, timeout_seconds: int) -> dict:
    validate_port(port)
    command = ["sudo", "-n", str(switch_command), str(port)]
    report = {"port": port, "command": command, "execute": execute}
    if not execute:
        return report
    if not health_ok(port):
        raise ReleaseError(f"refusing cutover: backend on port {port} is not healthy")
    result = run_command(command, timeout=60)
    if result.returncode != 0:
        raise ReleaseError(f"cutover command failed:\n{result.stdout}")
    wait_for_health(port, timeout_seconds=timeout_seconds)
    report["health"] = "ok"
    return report


def stop_old_port(port: int, *, execute: bool) -> dict:
    validate_port(port)
    command = ["sudo", "-n", "/usr/bin/systemctl", "stop", f"game-video-tool@{port}.service"]
    report = {"port": port, "command": command, "execute": execute}
    if not execute:
        return report
    result = run_command(command, timeout=60)
    if result.returncode != 0:
        raise ReleaseError(f"failed to stop old service:\n{result.stdout}")
    return report


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Blue/green release helper for Game Video Tool")
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--switch-command", type=Path, default=DEFAULT_SWITCH_COMMAND)
    parser.add_argument("--health-timeout-seconds", type=int, default=45)
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight")
    preflight.add_argument("--package", type=Path, required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--package", type=Path, required=True)
    prepare.add_argument("--release-id", required=True)
    prepare.add_argument("--preserve-assets-from", type=Path, default=None)
    prepare.add_argument("--execute", action="store_true")

    standby = sub.add_parser("start-standby")
    standby.add_argument("--release-id", required=True)
    standby.add_argument("--standby-port", type=int, default=None)
    standby.add_argument("--execute", action="store_true")

    switch = sub.add_parser("cutover")
    switch.add_argument("--standby-port", type=int, required=True)
    switch.add_argument("--stop-old-port", type=int, default=None)
    switch.add_argument("--force-stop-old", action="store_true")
    switch.add_argument("--execute", action="store_true")

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "preflight":
            inspection = inspect_package(args.package)
            print_json({
                "success": inspection.ok,
                "package": str(args.package),
                "member_count": inspection.member_count,
                "required_found": inspection.required_found,
                "errors": inspection.errors,
            })
            return 0 if inspection.ok else 1
        if args.command == "prepare":
            report = prepare_release(
                args.package,
                args.runtime_dir,
                args.release_id,
                execute=args.execute,
                preserve_assets_from=args.preserve_assets_from,
            )
            print_json({"success": True, "step": "prepare", **report})
            return 0
        if args.command == "start-standby":
            active = read_active_port(args.runtime_dir)
            standby_port = validate_port(args.standby_port or other_port(active))
            slot_report = point_slot(args.runtime_dir, standby_port, args.release_id, execute=args.execute)
            service_report = start_service(standby_port, execute=args.execute, timeout_seconds=args.health_timeout_seconds)
            print_json({"success": True, "step": "start-standby", "active_port": active, "slot": slot_report, "service": service_report})
            return 0
        if args.command == "cutover":
            standby_port = validate_port(args.standby_port)
            switch_report = cutover(standby_port, args.switch_command, execute=args.execute, timeout_seconds=args.health_timeout_seconds)
            stop_report = None
            if args.stop_old_port is not None:
                if not args.force_stop_old:
                    raise ReleaseError("refusing to stop old port during cutover without --force-stop-old; observe first, then stop old port explicitly")
                stop_report = stop_old_port(validate_port(args.stop_old_port), execute=args.execute)
            print_json({"success": True, "step": "cutover", "switch": switch_report, "stop_old": stop_report})
            return 0
    except ReleaseError as exc:
        fail(str(exc))
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
