from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_release_module():
    spec = importlib.util.spec_from_file_location("zero_downtime_release", ROOT / "deploy" / "zero-downtime-release.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_package(path: Path, members: dict[str, str]):
    with tarfile.open(path, "w:gz") as tar:
        for name, text in members.items():
            tmp = path.parent / name.replace("/", "_")
            tmp.write_text(text, encoding="utf-8")
            tar.add(tmp, arcname=name)
            tmp.unlink()


class ZeroDowntimeReleaseTests(unittest.TestCase):
    def test_preflight_accepts_clean_release_package(self):
        rel = load_release_module()
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "release.tar.gz"
            make_package(package, {
                "game-video-tool/server/main.py": "print('ok')\n",
                "game-video-tool/react-ui/dist/index.html": "<html></html>\n",
            })

            report = rel.inspect_package(package)

        self.assertTrue(report.ok)
        self.assertEqual(report.errors, [])
        self.assertIn("game-video-tool/server/main.py", report.required_found)

    def test_preflight_rejects_secrets_and_missing_dist(self):
        rel = load_release_module()
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "release.tar.gz"
            make_package(package, {
                "game-video-tool/server/main.py": "print('ok')\n",
                "game-video-tool/.env": "SECRET=1\n",
            })

            report = rel.inspect_package(package)

        self.assertFalse(report.ok)
        self.assertTrue(any(".env" in error for error in report.errors))
        self.assertTrue(any("react-ui/dist/index.html" in error for error in report.errors))

    def test_port_helpers_are_strict(self):
        rel = load_release_module()

        self.assertEqual(rel.other_port(57991), 57992)
        self.assertEqual(rel.other_port(57992), 57991)
        self.assertEqual(rel.validate_release_id("release-20260508_01"), "release-20260508_01")
        with self.assertRaises(rel.ReleaseError):
            rel.validate_port(58000)
        with self.assertRaises(rel.ReleaseError):
            rel.validate_release_id("../escape")

    def test_preflight_rejects_symlink_members(self):
        rel = load_release_module()
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "release.tar.gz"
            target = Path(tmp) / "target.txt"
            target.write_text("x", encoding="utf-8")
            with tarfile.open(package, "w:gz") as tar:
                tar.add(target, arcname="game-video-tool/server/main.py")
                info = tarfile.TarInfo("game-video-tool/react-ui/dist/index.html")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tar.addfile(info)

            report = rel.inspect_package(package)

        self.assertFalse(report.ok)
        self.assertTrue(any("unsupported tar member type" in error for error in report.errors))

    def test_extract_checked_package_rechecks_before_extracting(self):
        rel = load_release_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "release.tar.gz"
            target = tmp_path / "target"
            make_package(package, {
                "game-video-tool/server/main.py": "print('ok')\n",
                "game-video-tool/.env": "SECRET=1\n",
            })

            with self.assertRaises(rel.ReleaseError):
                rel.extract_checked_package(package, target)

            self.assertFalse(target.exists())

    def test_active_port_defaults_to_current_single_instance_port(self):
        rel = load_release_module()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(rel.read_active_port(Path(tmp)), 57991)
            (Path(tmp) / "active-port").write_text("57992\n", encoding="utf-8")
            self.assertEqual(rel.read_active_port(Path(tmp)), 57992)

    def test_dry_run_does_not_run_systemctl_or_cutover(self):
        rel = load_release_module()

        with mock.patch.object(rel, "run_command") as run_command:
            service_report = rel.start_service(57992, execute=False, timeout_seconds=1)
            cutover_report = rel.cutover(57992, Path("/usr/local/sbin/game-video-switch-upstream"), execute=False, timeout_seconds=1)

        run_command.assert_not_called()
        self.assertFalse(service_report["execute"])
        self.assertFalse(cutover_report["execute"])

    def test_cutover_refuses_to_stop_old_port_without_force_flag(self):
        rel = load_release_module()

        with mock.patch.object(rel, "health_ok", return_value=True), \
                mock.patch.object(rel, "run_command") as run_command, \
                redirect_stdout(io.StringIO()), \
                self.assertRaises(SystemExit):
            rel.main(["cutover", "--standby-port", "57992", "--stop-old-port", "57991"])

        run_command.assert_not_called()

    def test_switch_script_only_allows_known_ports(self):
        script = (ROOT / "deploy" / "game-video-switch-upstream.sh").read_text(encoding="utf-8")

        self.assertIn("57991|57992", script)
        self.assertIn("candidate backend is not healthy", script)
        self.assertIn("nginx -t", script)
        self.assertIn("nginx -s reload", script)

    def test_preserve_frontend_assets_keeps_old_hashed_chunks(self):
        rel = load_release_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_assets = tmp_path / "source" / "assets"
            target_assets = tmp_path / "release" / "react-ui" / "dist" / "assets"
            source_assets.mkdir(parents=True)
            target_assets.mkdir(parents=True)
            (source_assets / "old.js").write_text("old", encoding="utf-8")
            (source_assets / "old.css").write_text("old", encoding="utf-8")
            (source_assets / "video.mp4").write_text("skip", encoding="utf-8")
            (target_assets / "new.js").write_text("new", encoding="utf-8")

            report = rel.preserve_frontend_assets(tmp_path / "release", tmp_path / "source")

            self.assertEqual(report["preserved_count"], 2)
            self.assertTrue((target_assets / "old.js").exists())
            self.assertTrue((target_assets / "old.css").exists())
            self.assertFalse((target_assets / "video.mp4").exists())

    def test_blue_green_nginx_template_preserves_login_rate_limit(self):
        conf = (ROOT / "deploy" / "nginx-game-video-tool-blue-green.conf.example").read_text(encoding="utf-8")

        self.assertIn("limit_req_zone", conf)
        self.assertIn("location = /api/auth/login", conf)
        self.assertIn("limit_req zone=login_zone", conf)


if __name__ == "__main__":
    unittest.main()
