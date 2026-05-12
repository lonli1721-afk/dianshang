from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_watch_module():
    spec = importlib.util.spec_from_file_location("server_health_watch", ROOT / "deploy" / "server-health-watch.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def args_for(tmp_path: Path, **overrides):
    values = {
        "app_dir": tmp_path / "app",
        "data_dir": tmp_path / "data",
        "backup_dir": tmp_path / "backups",
        "report_dir": tmp_path / "backups" / "health-watch",
        "service_name": "game-video-tool.service",
        "health_url": "http://127.0.0.1:57991/health",
        "provider_queue_url": "http://127.0.0.1:57991/ops/provider-queue",
        "health_timeout_seconds": 3,
        "provider_queue_timeout_seconds": 3,
        "command_timeout_seconds": 5,
        "since_hours": 24,
        "log_tail_lines": 5000,
        "journal_tail_lines": 200,
        "top_users": 10,
        "top_memory_processes": 8,
        "cloud_dbs_keep_count": 200,
        "disk_warn_percent": 70,
        "disk_block_percent": 90,
        "disk_min_free_gb": 5,
        "memory_warn_mb": 1200,
        "memory_critical_mb": 1600,
        "retention_hours": 24 * 7,
        "keep_latest_count": 200,
        "no_write": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def health_payload(**overrides):
    payload = {
        "health": {"ok": True, "status_code": 200},
        "disk": [
            {
                "path": "/home/deploy/game-video-data",
                "exists": True,
                "used_percent": 50.0,
                "free_bytes": 25 * 1024**3,
            }
        ],
        "tasks": {
            "db_errors": [],
            "stale_processing_by_provider": {},
            "recent_error_categories": {},
        },
        "provider_queue": {
            "ok": True,
            "body": {
                "snapshot": {
                    "providers": {},
                    "status_queries": {"providers": {}},
                    "key_pools": {},
                }
            },
        },
        "logs": {
            "error_counts": {
                "http_429": 0,
                "http_503": 0,
                "http_504": 0,
                "failed_fetch": 0,
                "traceback": 0,
            }
        },
        "memory": {
            "service": {
                "available": True,
                "status": "ok",
                "rss_bytes": 256 * 1024 * 1024,
                "peak_rss_bytes": 300 * 1024 * 1024,
            }
        },
    }
    payload.update(overrides)
    return payload


class ServerHealthWatchTests(unittest.TestCase):
    def test_classify_ok_warning_and_critical(self):
        watch = load_watch_module()
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(Path(tmp))
            service = {"active": True}
            journal = {"error_counts": {"traceback": 0, "http_503": 0, "http_504": 0, "failed_fetch": 0, "http_429": 0}}

            severity, findings = watch.classify_watch(service, health_payload(), journal, args)
            self.assertEqual(severity, "ok")
            self.assertIn("No immediate blocker", findings[0])

            warning_payload = health_payload(tasks={"db_errors": [], "stale_processing_by_provider": {"seedance": 1}, "recent_error_categories": {}})
            severity, findings = watch.classify_watch(service, warning_payload, journal, args)
            self.assertEqual(severity, "warning")
            self.assertIn("stale_processing:1", findings)

            critical_service = {"active": False}
            severity, findings = watch.classify_watch(critical_service, health_payload(), journal, args)
            self.assertEqual(severity, "critical")
            self.assertIn("service_not_active", findings)

            memory_warning_payload = health_payload(memory={"service": {"available": True, "status": "warning"}})
            severity, findings = watch.classify_watch(service, memory_warning_payload, journal, args)
            self.assertEqual(severity, "warning")
            self.assertIn("memory_warning", findings)

    def test_provider_queue_pressure_detects_waiting_rows(self):
        watch = load_watch_module()
        provider_queue = {
            "ok": True,
            "body": {
                "snapshot": {
                    "providers": {"gemini": {"waiting": 1, "saturated": False, "total_timeouts": 0}},
                    "status_queries": {"providers": {"ark": {"waiting": 0, "saturated": True, "total_timeouts": 0}}},
                    "key_pools": {"global": {"project": {"waiting": 0, "total_queue_timeouts": 1}}},
                }
            },
        }

        pressure = watch.provider_queue_pressure(provider_queue)

        self.assertIn("provider:gemini", pressure)
        self.assertIn("status_query:ark", pressure)
        self.assertIn("key_pool:global", pressure)

    def test_write_reports_creates_latest_and_timestamped_files(self):
        watch = load_watch_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            args = args_for(tmp_path)
            payload = {
                "created_at": "2026-05-05T16:00:00+08:00",
                "severity": "ok",
                "findings": ["No immediate blocker found by server-side health watch."],
                "summary": {
                    "service_active": True,
                    "health_ok": True,
                    "stale_processing_count": 0,
                    "db_errors_count": 0,
                    "provider_queue_pressure": [],
                    "disk": [{"path": "/data", "used_percent": 50, "free_bytes": 1024}],
                },
            }

            outputs = watch.write_reports(args, payload)

            self.assertTrue(Path(outputs["json_report"]).exists())
            self.assertTrue(Path(outputs["text_report"]).exists())
            self.assertTrue((args.report_dir / "health-watch-latest.json").exists())
            self.assertTrue((args.report_dir / "health-watch-latest.txt").exists())

    def test_cleanup_retention_only_deletes_old_health_watch_reports(self):
        watch = load_watch_module()
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            old_json = report_dir / "health-watch-20260501-010000.json"
            old_txt = report_dir / "health-watch-20260501-010000.txt"
            unrelated = report_dir / "media-cleanup-plan.json"
            latest = report_dir / "health-watch-latest.json"
            for path in (old_json, old_txt, unrelated, latest):
                path.write_text("x", encoding="utf-8")
            old_ts = time.time() - 10 * 24 * 3600
            os.utime(old_json, (old_ts, old_ts))
            os.utime(old_txt, (old_ts, old_ts))
            os.utime(unrelated, (old_ts, old_ts))
            os.utime(latest, (old_ts, old_ts))

            deleted = watch.cleanup_retention(report_dir, retention_hours=24, keep_latest_count=0)

            self.assertEqual({Path(path).name for path in deleted}, {old_json.name, old_txt.name})
            self.assertFalse(old_json.exists())
            self.assertFalse(old_txt.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(latest.exists())

    def test_build_watch_report_uses_readonly_collectors(self):
        watch = load_watch_module()
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(Path(tmp))
            fake_health_module = SimpleNamespace(build_report=mock.Mock(return_value=health_payload()), ERROR_PATTERNS={
                "http_429": mock.Mock(search=lambda _line: False),
                "http_503": mock.Mock(search=lambda _line: False),
                "http_504": mock.Mock(search=lambda _line: False),
                "failed_fetch": mock.Mock(search=lambda _line: False),
                "traceback": mock.Mock(search=lambda _line: False),
            })

            with mock.patch.object(watch, "load_health_report_module", return_value=fake_health_module), \
                    mock.patch.object(watch, "service_status", return_value={"active": True}), \
                    mock.patch.object(watch, "journal_report", return_value={"ok": True, "error_counts": {}}):
                payload = watch.build_watch_report(args)

        self.assertTrue(payload["readonly"])
        self.assertTrue(payload["writes_reports_only"])
        self.assertEqual(payload["severity"], "ok")


if __name__ == "__main__":
    unittest.main()
