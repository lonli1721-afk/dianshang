#!/usr/bin/env python3
"""Read-only preflight for enabling blue/green releases.

This script is safe to run on production before the R3 infrastructure change.
It reads service, nginx, port, and sudo capability state, then reports blockers.
It never writes nginx/systemd/sudoers files and never restarts services.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.request import urlopen


DEFAULT_APP_DIR = Path("/home/deploy/game-video-tool")
DEFAULT_DATA_DIR = Path("/home/deploy/game-video-data")
DEFAULT_BACKUP_DIR = Path("/home/deploy/game-video-backups")
DEFAULT_RUNTIME_DIR = Path("/home/deploy/game-video-runtime")
DEFAULT_NGINX_DIR = Path("/etc/nginx")
ALLOWED_PORTS = (57991, 57992)
DIRECT_BACKEND_RE = re.compile(r"127\.0\.0\.1:(57991|57992)")


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: dict
    severity: str = "ok"


def run_command(command: list[str], timeout_seconds: int = 5) -> dict:
    try:
        proc = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
        return {"returncode": proc.returncode, "output": proc.stdout.strip()}
    except Exception as exc:
        return {"returncode": -1, "output": str(exc)}


def port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def health_ok(port: int, timeout_seconds: float = 2.0) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout_seconds) as response:
            return response.status == 200
    except Exception:
        return False


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def collect_nginx_refs(nginx_dir: Path) -> dict:
    files: list[dict] = []
    direct_refs: list[dict] = []
    upstream_includes: list[dict] = []
    login_rate_limit = False
    if nginx_dir.exists():
        paths = {path for path in nginx_dir.rglob("*.conf")}
        paths.add(nginx_dir / "nginx.conf")
        for path in sorted(paths):
            if not path.exists() or not path.is_file():
                continue
            text = read_text(path)
            if not text:
                continue
            rel = str(path)
            files.append({"path": rel})
            if "limit_req_zone" in text and "login_zone" in text:
                login_rate_limit = True
            if "game-video-tool-upstream.inc" in text or "$game_video_backend" in text:
                upstream_includes.append({"path": rel})
            for lineno, line in enumerate(text.splitlines(), start=1):
                if DIRECT_BACKEND_RE.search(line):
                    direct_refs.append({"path": rel, "line": lineno, "text": line.strip()})
    return {
        "files_scanned": files,
        "direct_backend_refs": direct_refs,
        "upstream_includes": upstream_includes,
        "login_rate_limit_present": login_rate_limit,
    }


def sudo_check(command: list[str]) -> dict:
    # sudo -l checks whether a command is allowed without executing it.
    # This keeps the preflight read-only even after sudoers rules are installed.
    return run_command(["sudo", "-n", "-l", *command], timeout_seconds=5)


def read_active_port(runtime_dir: Path) -> int:
    try:
        value = int((runtime_dir / "active-port").read_text(encoding="utf-8").strip())
        if value in ALLOWED_PORTS:
            return value
    except Exception:
        pass
    return 57991


def other_port(port: int) -> int:
    return 57992 if port == 57991 else 57991


def build_report(args: argparse.Namespace) -> dict:
    app_dir = args.app_dir
    data_dir = args.data_dir
    backup_dir = args.backup_dir
    runtime_dir = args.runtime_dir
    nginx_dir = args.nginx_dir

    checks: list[CheckResult] = []

    active_port = read_active_port(runtime_dir)
    inactive_port = other_port(active_port)
    active_service_name = args.service_name if active_port == 57991 else f"game-video-tool@{active_port}.service"
    service = run_command(["systemctl", "show", active_service_name, "-p", "ActiveState", "-p", "MainPID", "-p", "FragmentPath", "--no-pager"])
    service["active_port"] = active_port
    service["inactive_port"] = inactive_port
    service["service_name"] = active_service_name
    service_ok = "ActiveState=active" in service["output"]
    checks.append(CheckResult("active_service_running", service_ok, service, "critical" if not service_ok else "ok"))

    ports = {
        str(port): {"listening": port_listening(port), "health_ok": health_ok(port) if port_listening(port) else False}
        for port in ALLOWED_PORTS
    }
    active_state = ports[str(active_port)]
    inactive_state = ports[str(inactive_port)]
    inactive_state["port"] = inactive_port
    inactive_state["note"] = "inactive port may remain running briefly as rollback capacity after cutover"
    checks.append(CheckResult("inactive_port_available_for_next_release", not inactive_state["listening"], inactive_state, "warning" if inactive_state["listening"] else "ok"))
    checks.append(CheckResult("active_port_healthy", bool(active_state["health_ok"]), active_state, "critical" if not active_state["health_ok"] else "ok"))

    dirs = {
        "app_dir": {"path": str(app_dir), "exists": app_dir.exists(), "is_dir": app_dir.is_dir()},
        "data_dir": {"path": str(data_dir), "exists": data_dir.exists(), "is_dir": data_dir.is_dir()},
        "backup_dir": {"path": str(backup_dir), "exists": backup_dir.exists(), "is_dir": backup_dir.is_dir()},
        "runtime_dir": {"path": str(runtime_dir), "exists": runtime_dir.exists(), "is_dir": runtime_dir.is_dir()},
    }
    required_dirs_ok = all(dirs[name]["is_dir"] for name in ("app_dir", "data_dir", "backup_dir", "runtime_dir"))
    checks.append(CheckResult("required_directories", required_dirs_ok, dirs, "critical" if not required_dirs_ok else "ok"))

    nginx = collect_nginx_refs(nginx_dir)
    direct_refs = nginx["direct_backend_refs"]
    has_blue_green_include = bool(nginx["upstream_includes"])
    nginx_ready = has_blue_green_include and not direct_refs and nginx["login_rate_limit_present"]
    checks.append(CheckResult(
        "nginx_blue_green_ready",
        nginx_ready,
        nginx,
        "critical" if not nginx_ready else "ok",
    ))

    sudoers = {
        "systemctl_restart_57991": sudo_check(["/usr/bin/systemctl", "restart", "game-video-tool@57991.service"]),
        "systemctl_restart_57992": sudo_check(["/usr/bin/systemctl", "restart", "game-video-tool@57992.service"]),
        "systemctl_stop_57991": sudo_check(["/usr/bin/systemctl", "stop", "game-video-tool@57991.service"]),
        "systemctl_stop_57992": sudo_check(["/usr/bin/systemctl", "stop", "game-video-tool@57992.service"]),
        "switch_to_57991": sudo_check(["/usr/local/sbin/game-video-switch-upstream", "57991"]),
        "switch_to_57992": sudo_check(["/usr/local/sbin/game-video-switch-upstream", "57992"]),
    }
    sudo_ready = all(item["returncode"] == 0 for item in sudoers.values())
    checks.append(CheckResult("sudoers_minimal_commands_ready", sudo_ready, sudoers, "critical" if not sudo_ready else "ok"))

    script_paths = {
        "zero_downtime_release": app_dir / "deploy" / "zero-downtime-release.py",
        "switch_upstream": app_dir / "deploy" / "game-video-switch-upstream.sh",
        "service_template": app_dir / "deploy" / "game-video-tool@.service",
        "nginx_template": app_dir / "deploy" / "nginx-game-video-tool-blue-green.conf.example",
    }
    scripts = {name: {"path": str(path), "exists": path.exists()} for name, path in script_paths.items()}
    scripts_ok = all(item["exists"] for item in scripts.values())
    checks.append(CheckResult("release_tooling_present", scripts_ok, scripts, "critical" if not scripts_ok else "ok"))

    disk = run_command(["df", "-h", str(app_dir)], timeout_seconds=5)
    checks.append(CheckResult("disk_snapshot", disk["returncode"] == 0, disk, "warning" if disk["returncode"] != 0 else "ok"))

    blockers = [check.name for check in checks if check.severity == "critical" and not check.ok]
    warnings = [check.name for check in checks if check.severity == "warning" and not check.ok]

    return {
        "readonly": True,
        "success": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "checks": [check.__dict__ for check in checks],
        "recommended_next_steps": recommended_next_steps(blockers),
    }


def recommended_next_steps(blockers: list[str]) -> list[str]:
    steps: list[str] = []
    if "required_directories" in blockers:
        steps.append("Create and chown /home/deploy/game-video-runtime before enabling standby releases.")
    if "release_tooling_present" in blockers:
        steps.append("Deploy the zero-downtime tooling package before enabling blue/green cutover.")
    if "nginx_blue_green_ready" in blockers:
        steps.append("Replace every nginx 127.0.0.1:57991 proxy path with the blue/green upstream include and preserve login rate limiting.")
    if "sudoers_minimal_commands_ready" in blockers:
        steps.append("Install least-privilege sudoers rules for only game-video-tool@57991/57992 and game-video-switch-upstream.")
    if "active_service_running" in blockers or "active_port_healthy" in blockers:
        steps.append("Do not change infrastructure until the current production service is healthy.")
    if not steps:
        steps.append("Infrastructure preflight is green; proceed to R3 install only with explicit approval and backups.")
    return steps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only blue/green infrastructure preflight")
    parser.add_argument("--app-dir", type=Path, default=DEFAULT_APP_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--nginx-dir", type=Path, default=DEFAULT_NGINX_DIR)
    parser.add_argument("--service-name", default="game-video-tool.service")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"success: {report['success']}")
        print(f"blockers: {', '.join(report['blockers']) if report['blockers'] else 'none'}")
        print(f"warnings: {', '.join(report['warnings']) if report['warnings'] else 'none'}")
        print("recommended_next_steps:")
        for step in report["recommended_next_steps"]:
            print(f"- {step}")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
