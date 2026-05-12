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


def load_task_stale_watch_module():
    spec = importlib.util.spec_from_file_location("task_stale_watch", ROOT / "deploy" / "task-stale-watch.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def create_fixture(data_dir: Path, *, stale: bool) -> None:
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
            prompt TEXT DEFAULT '',
            provider TEXT DEFAULT '',
            model TEXT DEFAULT '',
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
    updated_at = now - timedelta(minutes=10 if stale else 1)
    ts = updated_at.isoformat().replace("+00:00", "Z")
    conn.execute("INSERT INTO game_projects (id, name) VALUES (?,?)", ("project-1", "Demo"))
    conn.execute(
        """
        INSERT INTO game_tasks
        (id, project_id, type, prompt, provider, model, status, external_task_id, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        ("task-1", "project-1", "generate", "prompt", "jimeng", "seedance-2.0", "processing", "external-1", ts, ts),
    )
    conn.commit()
    conn.close()


class TaskStaleWatchTests(unittest.TestCase):
    def test_report_warns_about_stale_tasks_without_repairing(self):
        watch = load_task_stale_watch_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            create_fixture(data_dir, stale=True)
            args = watch.build_parser().parse_args(["--data-dir", str(data_dir), "--stale-seconds", "300"])

            payload = watch.build_watch_report(args)

        self.assertTrue(payload["readonly"])
        self.assertFalse(payload["mutates_database"])
        self.assertFalse(payload["calls_provider_api"])
        self.assertFalse(payload["repairs_tasks"])
        self.assertEqual(payload["severity"], "warning")
        self.assertEqual(payload["stale_processing_count"], 1)
        self.assertEqual(payload["stale_processing_sample"][0]["username"], "alice")
        self.assertEqual(payload["stale_processing_sample"][0]["external_task_id"], "external-1")

    def test_report_is_ok_when_no_task_exceeds_threshold(self):
        watch = load_task_stale_watch_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            create_fixture(data_dir, stale=False)
            args = watch.build_parser().parse_args(["--data-dir", str(data_dir), "--stale-seconds", "300"])

            payload = watch.build_watch_report(args)

        self.assertEqual(payload["severity"], "ok")
        self.assertEqual(payload["stale_processing_count"], 0)

    def test_write_report_dir_creates_latest_and_cleans_only_watch_reports(self):
        watch = load_task_stale_watch_module()
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            old_json = report_dir / "task-stale-watch-20260501-010000.json"
            old_txt = report_dir / "task-stale-watch-20260501-010000.txt"
            latest = report_dir / "task-stale-watch-latest.json"
            unrelated = report_dir / "health-watch-20260501-010000.json"
            for path in (old_json, old_txt, latest, unrelated):
                path.write_text("x", encoding="utf-8")
            old_ts = time.time() - 10 * 24 * 3600
            for path in (old_json, old_txt, latest, unrelated):
                os.utime(path, (old_ts, old_ts))
            payload = {
                "severity": "ok",
                "readonly": True,
                "threshold_seconds": 300,
                "stale_processing_count": 0,
                "stale_processing_by_provider": {},
                "db_errors": [],
                "recommendations": ["未发现超过阈值的 processing 任务。"],
            }

            outputs = watch.write_report_dir(report_dir, payload, retention_hours=24, keep_latest_count=0)

            self.assertTrue(Path(outputs["json_report"]).exists())
            self.assertTrue(Path(outputs["text_report"]).exists())
            self.assertTrue((report_dir / "task-stale-watch-latest.json").exists())
            self.assertTrue((report_dir / "task-stale-watch-latest.txt").exists())
            self.assertFalse(old_json.exists())
            self.assertFalse(old_txt.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
