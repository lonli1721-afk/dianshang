from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_task_state_audit_module():
    spec = importlib.util.spec_from_file_location("task_state_audit", ROOT / "deploy" / "task-state-audit.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def create_task_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
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
    conn.commit()
    conn.close()


class TaskStateAuditTests(unittest.TestCase):
    def test_audit_reports_stale_processing_with_user_context(self):
        task_state_audit = load_task_state_audit_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
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
            create_task_db(db_path)
            now = datetime.now(timezone.utc)
            stale = (now - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
            recent = now.isoformat().replace("+00:00", "Z")
            conn = sqlite3.connect(db_path)
            conn.execute("INSERT INTO game_projects (id, name) VALUES (?,?)", ("project-1", "Demo Project"))
            conn.execute(
                """
                INSERT INTO game_tasks
                (id, project_id, type, prompt, provider, model, status, external_task_id, error, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "task-stale",
                    "project-1",
                    "generate",
                    "A long prompt",
                    "jimeng",
                    "seedance-2.0",
                    "processing",
                    "external-1",
                    "",
                    stale,
                    stale,
                ),
            )
            conn.execute(
                """
                INSERT INTO game_tasks
                (id, project_id, provider, model, status, error, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                ("task-failed", "project-1", "gemini", "Gemini 3.1", "failed", "HTTP 429", recent, recent),
            )
            conn.commit()
            conn.close()

            payload = task_state_audit.audit_tasks(SimpleNamespace(
                data_dir=data_dir,
                stale_hours=2,
                since_hours=24,
                sample_limit=50,
                prompt_preview_chars=120,
            ))

        self.assertTrue(payload["readonly"])
        self.assertEqual(payload["stale_processing_count"], 1)
        self.assertEqual(payload["stale_processing_by_provider"]["jimeng"], 1)
        self.assertEqual(payload["stale_processing_by_user"]["user-a"]["username"], "alice")
        self.assertEqual(payload["recent_error_categories"]["rate_limited_429"], 1)
        self.assertEqual(payload["stale_processing_sample"][0]["project_name"], "Demo Project")
        self.assertEqual(
            payload["stale_processing_sample"][0]["candidate_action"],
            "wait_or_query_provider_status",
        )

    def test_orphan_processing_without_external_id_is_flagged(self):
        task_state_audit = load_task_state_audit_module()
        row = {"external_task_id": "", "provider": "jimeng"}

        self.assertEqual(
            task_state_audit.candidate_action(row, age_seconds=3 * 3600),
            "orphan_processing_without_external_task_id",
        )

    def test_provider_result_unavailable_error_is_classified(self):
        task_state_audit = load_task_state_audit_module()

        self.assertEqual(
            task_state_audit.classify_task_error("内容安全审核未通过。请调整提示词或更换图片/视频素材后重试。"),
            "content_safety",
        )

        self.assertEqual(
            task_state_audit.classify_task_error("视频任务已完成，但结果视频保存到本地失败：HTTP 403。请重新生成。"),
            "provider_video_remote_http_403",
        )
        self.assertEqual(
            task_state_audit.classify_task_error("视频任务已完成，但结果视频保存到本地失败：远程链接返回 HTTP 404。请重新生成。"),
            "provider_video_remote_http_404",
        )
        self.assertEqual(
            task_state_audit.classify_task_error("视频任务已完成，但结果视频保存到本地失败：未知错误。请重新生成。"),
            "provider_video_unknown_cache_error",
        )
        self.assertEqual(
            task_state_audit.classify_task_error("Arrearage Access denied, please make sure your account is in good standing."),
            "provider_billing_or_permission",
        )
        self.assertEqual(
            task_state_audit.classify_task_error("the parameter video total duration (seconds) must be less than or equal to 15.2"),
            "provider_reference_duration",
        )
        self.assertEqual(
            task_state_audit.classify_task_error("first/last frame content cannot be mixed with reference media content"),
            "provider_media_mix",
        )
        self.assertEqual(
            task_state_audit.classify_task_error("The parameter image_url is invalid: resource not found"),
            "provider_media_invalid",
        )


if __name__ == "__main__":
    unittest.main()
