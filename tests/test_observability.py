from __future__ import annotations

import importlib.util
import asyncio
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_health_report_module():
    spec = importlib.util.spec_from_file_location("health_report", ROOT / "deploy" / "health-report.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ObservabilityTests(unittest.TestCase):
    def test_classify_task_error(self):
        health_report = load_health_report_module()

        self.assertEqual(
            health_report.classify_task_error("HTTP 429 RESOURCE_EXHAUSTED"),
            "rate_limited_429",
        )
        self.assertEqual(
            health_report.classify_task_error("InvalidParameter.OversizeImage exceeds the limit"),
            "parameter_error",
        )
        self.assertEqual(
            health_report.classify_task_error("Arrearage Access denied, please make sure your account is in good standing."),
            "provider_billing_or_permission",
        )
        self.assertEqual(
            health_report.classify_task_error("first/last frame content cannot be mixed with reference media content"),
            "provider_media_mix",
        )
        self.assertEqual(
            health_report.classify_task_error("生成失败: Failed to fetch"),
            "network_fetch",
        )
        self.assertEqual(
            health_report.classify_task_error("内容安全审核未通过。请调整提示词或更换图片/视频素材后重试。"),
            "content_safety",
        )
        self.assertEqual(
            health_report.classify_task_error("上游任务已完成，但结果视频链接已过期或无法访问；请重新生成。"),
            "provider_result_unavailable",
        )
        self.assertEqual(
            health_report.classify_task_error("视频任务已完成，但上游未返回视频地址，请重新生成。"),
            "provider_video_missing_url",
        )
        self.assertEqual(
            health_report.classify_task_error("视频任务已完成，但结果视频保存到本地失败：远程链接返回 HTTP 403（content-type=text/html）。请重新生成。"),
            "provider_video_remote_http_403",
        )
        self.assertEqual(
            health_report.classify_task_error("视频任务已完成，但结果视频保存到本地失败：远程链接返回 HTTP 500。请重新生成。"),
            "provider_video_remote_http_5xx",
        )
        self.assertEqual(
            health_report.classify_task_error("视频任务已完成，但结果视频保存到本地失败：远程文件下载为空。请重新生成。"),
            "provider_video_empty_download",
        )
        self.assertEqual(
            health_report.classify_task_error("视频任务已完成，但结果视频保存到本地失败：本地写入失败：FileNotFoundError。请重新生成。"),
            "provider_video_local_write_failed",
        )

    def test_log_report_does_not_count_error_url_404_as_traceback(self):
        health_report = load_health_report_module()
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp)
            (app_dir / "app.log").write_text(
                'INFO:     162.243.173.145:0 - "GET /_layouts/15/error.aspx HTTP/1.1" 404 Not Found\n'
                'INFO:     166.88.26.169:0 - "GET /error HTTP/1.1" 404 Not Found\n'
                "ERROR: real application error\n",
                encoding="utf-8",
            )

            report = health_report.log_report(app_dir, tail_lines=100)

        self.assertEqual(report["error_counts"]["traceback"], 1)

    def test_log_report_separates_errors_after_latest_frontend_asset(self):
        health_report = load_health_report_module()
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp)
            (app_dir / "app.log").write_text(
                'INFO:     127.0.0.1:1 - "GET /assets/index-old.js HTTP/1.1" 200 OK\n'
                "Client render error user=a message=Cannot access '$t' before initialization\n"
                'INFO:     127.0.0.1:1 - "GET /assets/index-new.js HTTP/1.1" 200 OK\n'
                'INFO:     127.0.0.1:1 - "GET /health HTTP/1.1" 200 OK\n',
                encoding="utf-8",
            )

            report = health_report.log_report(app_dir, tail_lines=100)

        self.assertEqual(report["error_counts"]["traceback"], 1)
        self.assertEqual(report["latest_frontend_asset"]["asset"], "assets/index-new.js")
        self.assertEqual(report["latest_frontend_asset"]["error_counts_after"]["traceback"], 0)

    def test_log_report_summarizes_viral_observability(self):
        health_report = load_health_report_module()
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp)
            (app_dir / "app.log").write_text(
                "INFO VIRAL_OBS operation=analyze status=success provider=gemini model=gemini-2.5-pro "
                "duration_ms=1200.5 analysis_id=a1 video_count=2 tag_count=8 plan_count=0 "
                "target_count=0 selected_tag_count=0 chinese_retry=1 error_category=\n"
                "INFO VIRAL_OBS operation=plans status=failed provider=gemini model=gemini-2.5-pro "
                "duration_ms=50300 analysis_id=a1 video_count=0 tag_count=0 plan_count=0 "
                "target_count=0 selected_tag_count=3 chinese_retry=0 error_category=upstream_503\n",
                encoding="utf-8",
            )

            report = health_report.log_report(app_dir, tail_lines=100)

        viral = report["viral"]
        self.assertEqual(viral["sample_count"], 2)
        self.assertEqual(viral["by_operation"], {"analyze": 1, "plans": 1})
        self.assertEqual(viral["by_status"], {"success": 1, "failed": 1})
        self.assertEqual(viral["error_categories"], {"upstream_503": 1})
        self.assertEqual(viral["chinese_retry_by_operation"], {"analyze": 1})
        self.assertEqual(viral["duration_by_operation"]["plans"]["max_ms"], 50300.0)
        self.assertEqual(len(viral["slow_samples"]), 1)

    def test_db_task_report_counts_failure_categories_and_stale_processing(self):
        health_report = load_health_report_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            db_path = data_dir / "game_video.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE game_tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT DEFAULT '',
                    type TEXT DEFAULT 'generate',
                    prompt TEXT DEFAULT '',
                    character_refs TEXT DEFAULT '[]',
                    scene_refs TEXT DEFAULT '[]',
                    ref_video_path TEXT DEFAULT '',
                    model TEXT DEFAULT '',
                    provider TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    video_url TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    external_task_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            now = datetime.now(timezone.utc)
            recent = now.isoformat().replace("+00:00", "Z")
            stale = (now - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO game_tasks (id, provider, model, status, error, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                ("failed-1", "gemini", "Gemini 3.1 Pro", "failed", "HTTP 429 RESOURCE_EXHAUSTED", recent, recent),
            )
            conn.execute(
                "INSERT INTO game_tasks (id, provider, model, status, error, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                ("processing-1", "seedance", "Seedance 2.0 Fast", "processing", "", stale, stale),
            )
            conn.commit()
            conn.close()

            report = health_report.db_task_report(data_dir, hours=24)

        self.assertEqual(report["task_status_total"]["failed"], 1)
        self.assertEqual(report["recent_error_categories"]["rate_limited_429"], 1)
        self.assertEqual(report["recent_failed_by_provider"]["gemini"], 1)
        self.assertEqual(report["stale_processing_by_provider"]["seedance"], 1)

    def test_db_task_report_aggregates_user_databases(self):
        health_report = load_health_report_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            user_db_dir = data_dir / "users" / "user-a"
            user_db_dir.mkdir(parents=True)
            db_path = user_db_dir / "database.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE game_tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT DEFAULT '',
                    type TEXT DEFAULT 'generate',
                    prompt TEXT DEFAULT '',
                    character_refs TEXT DEFAULT '[]',
                    scene_refs TEXT DEFAULT '[]',
                    ref_video_path TEXT DEFAULT '',
                    model TEXT DEFAULT '',
                    provider TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    video_url TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    external_task_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            recent = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO game_tasks (id, provider, model, status, error, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                ("failed-user", "dashscope", "HappyHorse", "failed", "HTTP 503 UNAVAILABLE", recent, recent),
            )
            conn.commit()
            conn.close()

            report = health_report.db_task_report(data_dir, hours=24)

        self.assertEqual(report["db_count"], 1)
        self.assertEqual(report["recent_error_categories"]["upstream_503"], 1)
        self.assertEqual(report["recent_failed_by_provider"]["dashscope"], 1)

    def test_local_observability_rejects_forwarded_headers(self):
        sys.path.insert(0, str(ROOT / "server"))
        import observability  # noqa: PLC0415

        direct_request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})
        forwarded_request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"x-forwarded-for": "127.0.0.1"},
        )

        self.assertTrue(observability.is_local_observability_request(direct_request))
        self.assertFalse(observability.is_local_observability_request(forwarded_request))

    def test_provider_queue_snapshot_shape(self):
        sys.path.insert(0, str(ROOT / "server"))
        import provider_queue  # noqa: PLC0415

        async def scenario():
            provider_queue.get_provider_limiter("gemini")
            return provider_queue.provider_queue_snapshot()

        provider_queue._limiters.clear()
        snapshot = asyncio.run(scenario())

        self.assertIn("queue_timeout_seconds", snapshot)
        self.assertIn("providers", snapshot)
        self.assertGreaterEqual(snapshot["providers"]["gemini"]["limit"], 1)
        self.assertEqual(snapshot["providers"]["gemini"]["active"], 0)

    def test_memory_report_reads_proc_metrics_and_thresholds(self):
        health_report = load_health_report_module()
        with tempfile.TemporaryDirectory() as tmp:
            proc_root = Path(tmp)
            process_dir = proc_root / "123"
            fd_dir = process_dir / "fd"
            fd_dir.mkdir(parents=True)
            (fd_dir / "0").write_text("", encoding="utf-8")
            (process_dir / "cmdline").write_bytes(b"python3\x00server/main.py\x00")
            (process_dir / "status").write_text(
                "\n".join([
                    "Name:\tpython3",
                    "State:\tS (sleeping)",
                    "VmSize:\t  900000 kB",
                    "VmHWM:\t  1300000 kB",
                    "VmRSS:\t  1250000 kB",
                    "VmData:\t  700000 kB",
                    "VmSwap:\t       0 kB",
                    "Threads:\t9",
                ]),
                encoding="utf-8",
            )
            (proc_root / "meminfo").write_text(
                "\n".join([
                    "MemTotal:       8000000 kB",
                    "MemAvailable:   3000000 kB",
                    "SwapTotal:      1000000 kB",
                    "SwapFree:        900000 kB",
                ]),
                encoding="utf-8",
            )

            with mock.patch.object(health_report, "find_service_pid", return_value={"pid": 123, "method": "mock"}):
                report = health_report.memory_report(
                    "game-video-tool.service",
                    warn_mb=1200,
                    critical_mb=1600,
                    top_processes=3,
                    proc_root=proc_root,
                )

        self.assertTrue(report["service"]["available"])
        self.assertEqual(report["service"]["status"], "warning")
        self.assertEqual(report["service"]["threads"], 9)
        self.assertEqual(report["service"]["fd_count"], 1)
        self.assertEqual(report["system"]["memavailable_bytes"], 3000000 * 1024)
        self.assertEqual(report["top_processes"][0]["pid"], 123)


if __name__ == "__main__":
    unittest.main()
