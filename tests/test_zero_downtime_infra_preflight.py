from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
OK_COMMAND = {"returncode": 0, "output": "ok"}
SUDO_DENIED = {"returncode": 1, "output": "sudo: a password is required"}


def load_preflight_module():
    spec = importlib.util.spec_from_file_location("zero_downtime_infra_preflight", ROOT / "deploy" / "zero-downtime-infra-preflight.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def args_for(tmp_path: Path):
    return SimpleNamespace(
        app_dir=tmp_path / "app",
        data_dir=tmp_path / "data",
        backup_dir=tmp_path / "backups",
        runtime_dir=tmp_path / "runtime",
        nginx_dir=tmp_path / "nginx",
        service_name="game-video-tool.service",
    )


class ZeroDowntimeInfraPreflightTests(unittest.TestCase):
    def test_collect_nginx_refs_detects_direct_backend_and_rate_limit(self):
        preflight = load_preflight_module()
        with tempfile.TemporaryDirectory() as tmp:
            nginx = Path(tmp) / "nginx"
            confd = nginx / "conf.d"
            confd.mkdir(parents=True)
            (confd / "game-video-tool.conf").write_text(
                "limit_req_zone $binary_remote_addr zone=login_zone:10m rate=5r/s;\n"
                "proxy_pass http://127.0.0.1:57991;\n",
                encoding="utf-8",
            )

            refs = preflight.collect_nginx_refs(nginx)

        self.assertEqual(len(refs["direct_backend_refs"]), 1)
        self.assertTrue(refs["login_rate_limit_present"])
        self.assertFalse(refs["upstream_includes"])

    def test_report_blocks_when_sudo_and_nginx_are_not_ready(self):
        preflight = load_preflight_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            args = args_for(tmp_path)
            for path in (args.app_dir, args.data_dir, args.backup_dir, args.nginx_dir):
                path.mkdir(parents=True)
            (args.nginx_dir / "nginx.conf").write_text("proxy_pass http://127.0.0.1:57991;\n", encoding="utf-8")

            with mock.patch.object(preflight, "run_command", side_effect=[
                {"returncode": 0, "output": "ActiveState=active\nMainPID=1"},
                SUDO_DENIED,
                SUDO_DENIED,
                SUDO_DENIED,
                SUDO_DENIED,
                SUDO_DENIED,
                SUDO_DENIED,
                {"returncode": 0, "output": "df ok"},
            ]), \
                    mock.patch.object(preflight, "port_listening", side_effect=lambda port: port == 57991), \
                    mock.patch.object(preflight, "health_ok", return_value=True):
                report = preflight.build_report(args)

        self.assertFalse(report["success"])
        self.assertIn("nginx_blue_green_ready", report["blockers"])
        self.assertIn("sudoers_minimal_commands_ready", report["blockers"])

    def test_report_passes_when_blue_green_requirements_are_met(self):
        preflight = load_preflight_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            args = args_for(tmp_path)
            for path in (args.app_dir, args.data_dir, args.backup_dir, args.runtime_dir, args.nginx_dir):
                path.mkdir(parents=True)
            deploy = args.app_dir / "deploy"
            deploy.mkdir()
            for name in (
                "zero-downtime-release.py",
                "game-video-switch-upstream.sh",
                "game-video-tool@.service",
                "nginx-game-video-tool-blue-green.conf.example",
            ):
                (deploy / name).write_text("x", encoding="utf-8")
            (args.nginx_dir / "nginx.conf").write_text(
                "limit_req_zone $binary_remote_addr zone=login_zone:10m rate=5r/s;\n"
                "include /etc/nginx/conf.d/game-video-tool-upstream.inc;\n"
                "proxy_pass $game_video_backend;\n",
                encoding="utf-8",
            )

            with mock.patch.object(preflight, "run_command", side_effect=[
                {"returncode": 0, "output": "ActiveState=active\nMainPID=1"},
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                {"returncode": 0, "output": "df ok"},
            ]), \
                    mock.patch.object(preflight, "port_listening", side_effect=lambda port: port == 57991), \
                    mock.patch.object(preflight, "health_ok", return_value=True):
                report = preflight.build_report(args)

        self.assertTrue(report["success"])
        self.assertEqual(report["blockers"], [])

    def test_report_accepts_57992_as_active_with_57991_left_for_rollback(self):
        preflight = load_preflight_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            args = args_for(tmp_path)
            for path in (args.app_dir, args.data_dir, args.backup_dir, args.runtime_dir, args.nginx_dir):
                path.mkdir(parents=True)
            (args.runtime_dir / "active-port").write_text("57992", encoding="utf-8")
            deploy = args.app_dir / "deploy"
            deploy.mkdir()
            for name in (
                "zero-downtime-release.py",
                "game-video-switch-upstream.sh",
                "game-video-tool@.service",
                "nginx-game-video-tool-blue-green.conf.example",
            ):
                (deploy / name).write_text("x", encoding="utf-8")
            (args.nginx_dir / "nginx.conf").write_text(
                "limit_req_zone $binary_remote_addr zone=login_zone:10m rate=5r/s;\n"
                "proxy_pass $game_video_backend;\n",
                encoding="utf-8",
            )

            with mock.patch.object(preflight, "run_command", side_effect=[
                {"returncode": 0, "output": "ActiveState=active\nMainPID=2"},
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                {"returncode": 0, "output": "df ok"},
            ]), \
                    mock.patch.object(preflight, "port_listening", return_value=True), \
                    mock.patch.object(preflight, "health_ok", return_value=True):
                report = preflight.build_report(args)

        self.assertTrue(report["success"])
        self.assertEqual(report["warnings"], ["inactive_port_available_for_next_release"])


    def test_sudo_check_lists_permission_without_executing_command(self):
        preflight = load_preflight_module()

        with mock.patch.object(preflight, "run_command", return_value={"returncode": 0, "output": "allowed"}) as run_command:
            result = preflight.sudo_check(["/usr/local/sbin/game-video-switch-upstream", "57991"])

        self.assertEqual(result["returncode"], 0)
        run_command.assert_called_once_with(
            ["sudo", "-n", "-l", "/usr/local/sbin/game-video-switch-upstream", "57991"],
            timeout_seconds=5,
        )

    def test_missing_runtime_dir_blocks_ready_report(self):
        preflight = load_preflight_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            args = args_for(tmp_path)
            for path in (args.app_dir, args.data_dir, args.backup_dir, args.nginx_dir):
                path.mkdir(parents=True)
            deploy = args.app_dir / "deploy"
            deploy.mkdir()
            for name in (
                "zero-downtime-release.py",
                "game-video-switch-upstream.sh",
                "game-video-tool@.service",
                "nginx-game-video-tool-blue-green.conf.example",
            ):
                (deploy / name).write_text("x", encoding="utf-8")
            (args.nginx_dir / "nginx.conf").write_text(
                "limit_req_zone $binary_remote_addr zone=login_zone:10m rate=5r/s;\n"
                "proxy_pass $game_video_backend;\n",
                encoding="utf-8",
            )

            with mock.patch.object(preflight, "run_command", side_effect=[
                {"returncode": 0, "output": "ActiveState=active\nMainPID=1"},
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                OK_COMMAND,
                {"returncode": 0, "output": "df ok"},
            ]), \
                    mock.patch.object(preflight, "port_listening", side_effect=lambda port: port == 57991), \
                    mock.patch.object(preflight, "health_ok", return_value=True):
                report = preflight.build_report(args)

        self.assertFalse(report["success"])
        self.assertIn("required_directories", report["blockers"])
        self.assertTrue(any("game-video-runtime" in step for step in report["recommended_next_steps"]))


if __name__ == "__main__":
    unittest.main()
