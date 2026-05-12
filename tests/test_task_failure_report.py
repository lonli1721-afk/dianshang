from __future__ import annotations

import importlib.util
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_task_failure_report_module():
    spec = importlib.util.spec_from_file_location("task_failure_report", ROOT / "deploy" / "task-failure-report.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def create_fixture(data_dir: Path) -> None:
    auth = sqlite3.connect(data_dir / "auth.db")
    auth.executescript(
        """
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT,
            display_name TEXT,
            role TEXT,
            is_active INTEGER,
            team TEXT,
            last_login TEXT
        );
        """
    )
    auth.execute(
        "INSERT INTO users (id, username, display_name, role, is_active, team, last_login) VALUES (?,?,?,?,?,?,?)",
        ("user-a", "alice", "Alice", "user", 1, "creative", ""),
    )
    auth.commit()
    auth.close()

    db_path = data_dir / "users" / "user-a" / "database.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE game_projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE game_tasks (
            id TEXT PRIMARY KEY,
            project_id TEXT DEFAULT '',
            type TEXT NOT NULL DEFAULT 'generate',
            provider TEXT DEFAULT '',
            model TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            error TEXT DEFAULT '',
            external_task_id TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    now = datetime.now(timezone.utc)
    recent = now.isoformat().replace("+00:00", "Z")
    old = (now - timedelta(days=3)).isoformat().replace("+00:00", "Z")
    conn.execute("INSERT INTO game_projects (id, name) VALUES (?,?)", ("project-1", "Demo"))
    conn.execute(
        """
        INSERT INTO game_tasks
        (id, project_id, type, provider, model, status, error, external_task_id, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "task-429",
            "project-1",
            "generate",
            "gemini",
            "Gemini 3.1 Pro",
            "failed",
            "HTTP 429 RESOURCE_EXHAUSTED api_key=abcd1234abcd1234abcd1234abcd1234",
            "external-1",
            recent,
            recent,
        ),
    )
    conn.execute(
        """
        INSERT INTO game_tasks
        (id, project_id, type, provider, model, status, error, external_task_id, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        ("task-old", "project-1", "generate", "gemini", "Gemini", "failed", "HTTP 503", "external-old", old, old),
    )
    conn.commit()
    conn.close()


class TaskFailureReportTests(unittest.TestCase):
    def test_report_aggregates_recent_failures_without_repairing(self):
        report_module = load_task_failure_report_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            create_fixture(data_dir)
            args = report_module.build_parser().parse_args(["--data-dir", str(data_dir), "--since-hours", "24"])

            payload = report_module.build_failure_report(args)

        self.assertTrue(payload["readonly"])
        self.assertFalse(payload["mutates_database"])
        self.assertFalse(payload["calls_provider_api"])
        self.assertFalse(payload["repairs_tasks"])
        self.assertEqual(payload["severity"], "warning")
        self.assertEqual(payload["failed_count"], 1)
        self.assertEqual(payload["failed_by_category"]["rate_limited_429"], 1)
        self.assertEqual(payload["failed_by_provider"]["gemini"], 1)
        self.assertEqual(payload["failed_by_user"]["user-a"]["username"], "alice")
        self.assertEqual(payload["samples"][0]["project_name"], "Demo")

    def test_error_preview_is_redacted(self):
        report_module = load_task_failure_report_module()

        text = report_module.redact_text(
            "Authorization Bearer abcdefghijklmnopqrstuvwxyz123456 and api_key=abcd1234abcd1234abcd1234abcd1234",
            200,
        )

        self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", text)
        self.assertNotIn("abcd1234abcd1234abcd1234abcd1234", text)
        self.assertIn("***", text)

    def test_write_report_dir_creates_latest_and_cleans_only_failure_reports(self):
        report_module = load_task_failure_report_module()
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            old_json = report_dir / "task-failure-report-20260501-010000.json"
            old_txt = report_dir / "task-failure-report-20260501-010000.txt"
            latest = report_dir / "task-failure-report-latest.json"
            unrelated = report_dir / "task-stale-watch-20260501-010000.json"
            for path in (old_json, old_txt, latest, unrelated):
                path.write_text("x", encoding="utf-8")
            old_ts = time.time() - 10 * 24 * 3600
            for path in (old_json, old_txt, latest, unrelated):
                os.utime(path, (old_ts, old_ts))
            payload = {
                "created_at": "2026-05-07T00:00:00+08:00",
                "severity": "ok",
                "readonly": True,
                "since_hours": 24,
                "failed_count": 0,
                "failed_by_category": {},
                "failed_by_provider": {},
                "db_errors": [],
                "recommendations": ["最近窗口内没有失败任务。"],
            }

            outputs = report_module.write_report_dir(report_dir, payload, retention_hours=24, keep_latest_count=0)

            self.assertTrue(Path(outputs["json_report"]).exists())
            self.assertTrue(Path(outputs["text_report"]).exists())
            self.assertTrue((report_dir / "task-failure-report-latest.json").exists())
            self.assertTrue((report_dir / "task-failure-report-latest.txt").exists())
            self.assertFalse(old_json.exists())
            self.assertFalse(old_txt.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
