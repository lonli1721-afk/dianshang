from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_task_state_probe_module():
    spec = importlib.util.spec_from_file_location("task_state_probe", ROOT / "deploy" / "task-state-probe.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def create_failed_task_db(data_dir: Path, *, error: str) -> Path:
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
    conn.execute("INSERT INTO game_projects (id, name) VALUES (?,?)", ("project-1", "Demo"))
    conn.execute(
        """
        INSERT INTO game_tasks
        (id, project_id, type, prompt, provider, model, status, video_url, error,
         external_task_id, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "task-1",
            "project-1",
            "generate",
            "prompt",
            "jimeng",
            "seedance-2.0",
            "failed",
            "",
            error,
            "external-1",
            "2026-05-01T00:00:00Z",
            "2026-05-01T00:05:00Z",
        ),
    )
    conn.commit()
    conn.close()
    return db_path


class TaskStateProbeTests(unittest.TestCase):
    def test_select_seedance_candidates_requires_external_task_id(self):
        probe = load_task_state_probe_module()
        audit_payload = {
            "stale_processing_sample": [
                {"task_id": "a", "provider": "jimeng", "external_task_id": "external-a"},
                {"task_id": "b", "provider": "jimeng", "external_task_id": ""},
                {"task_id": "c", "provider": "happyhorse", "external_task_id": "external-c"},
            ]
        }

        candidates = probe.select_seedance_candidates(audit_payload, limit=10)

        self.assertEqual([item["task_id"] for item in candidates], ["a"])

    def test_select_wan_candidates_requires_external_task_id(self):
        probe = load_task_state_probe_module()
        audit_payload = {
            "stale_processing_sample": [
                {"task_id": "a", "provider": "wan", "external_task_id": "external-a"},
                {"task_id": "b", "provider": "wan", "external_task_id": ""},
                {"task_id": "c", "provider": "jimeng", "external_task_id": "external-c"},
            ]
        }

        candidates = probe.select_wan_candidates(audit_payload, limit=10)

        self.assertEqual([item["task_id"] for item in candidates], ["a"])

    def test_select_happyhorse_candidates_requires_external_task_id(self):
        probe = load_task_state_probe_module()
        audit_payload = {
            "stale_processing_sample": [
                {"task_id": "a", "provider": "happyhorse", "external_task_id": "external-a"},
                {"task_id": "b", "provider": "happyhorse", "external_task_id": ""},
                {"task_id": "c", "provider": "wan", "external_task_id": "external-c"},
            ]
        }

        candidates = probe.select_happyhorse_candidates(audit_payload, limit=10)

        self.assertEqual([item["task_id"] for item in candidates], ["a"])

    def test_probe_without_api_key_skips_network(self):
        probe = load_task_state_probe_module()
        with tempfile.TemporaryDirectory() as tmp:
            args = probe.build_parser().parse_args([
                "--data-dir", tmp,
                "--limit", "5",
            ])
            payload = asyncio.run(probe.run_probe(args))

        self.assertTrue(payload["readonly"])
        self.assertFalse(payload["api_key_present"])
        self.assertEqual(payload["probe_count"], 0)
        self.assertIn("No eligible", payload["recommendations"][0])

    def test_select_explicit_failed_candidates_requires_recoverable_error(self):
        probe = load_task_state_probe_module()
        task_audit = probe.load_task_audit_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            create_failed_task_db(
                data_dir,
                error="视频任务已完成，但结果视频保存到本地失败：远程链接返回 HTTP 403",
            )

            rows = probe.select_explicit_failed_candidates(data_dir, task_audit, {"task-1"}, limit=5)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "failed")
        self.assertEqual(rows[0]["external_task_id"], "external-1")
        self.assertEqual(rows[0]["error_category"], "provider_video_remote_http_403")

    def test_select_explicit_failed_candidates_skips_parameter_errors(self):
        probe = load_task_state_probe_module()
        task_audit = probe.load_task_audit_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            create_failed_task_db(data_dir, error="400 InvalidParameter: bad image size")

            rows = probe.select_explicit_failed_candidates(data_dir, task_audit, {"task-1"}, limit=5)

        self.assertEqual(rows, [])

    def test_run_probe_can_include_explicit_failed_task(self):
        probe = load_task_state_probe_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            create_failed_task_db(data_dir, error="结果视频保存到本地失败：未知错误")
            (data_dir / "settings.json").write_text(json.dumps({"game_ark_api_key": "key"}), encoding="utf-8")
            args = probe.build_parser().parse_args([
                "--data-dir", str(data_dir),
                "--task-id", "task-1",
                "--include-failed",
            ])
            original = probe.query_seedance_task
            probe.query_seedance_task = lambda _api_key, _task_id: {
                "status": "completed",
                "video_url": "https://example.com/video.mp4",
                "error": "",
                "raw_status": "succeeded",
            }
            try:
                payload = asyncio.run(probe.run_probe(args))
            finally:
                probe.query_seedance_task = original

        self.assertEqual(payload["candidate_counts"]["explicit_failed"], 1)
        self.assertEqual(payload["probe_count"], 1)
        self.assertEqual(payload["probes"][0]["local_status"], "failed")
        self.assertEqual(payload["probes"][0]["provider_status"], "completed")

    def test_recommended_action_from_probe(self):
        probe = load_task_state_probe_module()

        self.assertEqual(
            probe.recommended_action_from_probe({"status": "completed", "video_url": "https://example.com/a.mp4"}),
            "can_repair_to_completed_after_cache_policy_review",
        )
        self.assertEqual(
            probe.recommended_action_from_probe({"status": "failed", "error": "x"}),
            "can_repair_to_failed_after_review",
        )

    def test_seedance_response_helpers(self):
        probe = load_task_state_probe_module()

        self.assertEqual(probe.map_seedance_status("succeeded"), "completed")
        self.assertEqual(probe.map_seedance_status("failed"), "failed")
        self.assertEqual(probe.map_seedance_status("running"), "processing")
        self.assertEqual(
            probe.extract_ark_video_url({"content": {"video_url": "https://example.com/video.mp4"}}),
            "https://example.com/video.mp4",
        )

    def test_wan_response_helpers(self):
        probe = load_task_state_probe_module()

        self.assertEqual(probe.map_wan_status("SUCCEEDED"), "completed")
        self.assertEqual(probe.map_wan_status("FAILED"), "failed")
        self.assertEqual(probe.map_wan_status("RUNNING"), "processing")
        self.assertEqual(
            probe.extract_dashscope_video_url({"results": {"video_url": "https://example.com/wan.mp4"}}, {}),
            "https://example.com/wan.mp4",
        )

    def test_query_seedance_statuses_preserves_repair_evidence(self):
        probe = load_task_state_probe_module()
        candidates = [{
            "db": "/data/users/user-a/database.db",
            "task_id": "local-1",
            "external_task_id": "external-1",
            "user_id": "user-a",
            "username": "alice",
            "display_name": "Alice",
            "team": "creative",
            "project_id": "project-1",
            "project_name": "Demo",
            "provider": "jimeng",
            "model": "seedance-2.0",
            "updated_at": "2026-05-01T00:00:00Z",
            "created_at": "2026-05-01T00:00:00Z",
        }]

        original = probe.query_seedance_task
        probe.query_seedance_task = lambda _api_key, _task_id: {
            "status": "completed",
            "video_url": "https://example.com/video.mp4",
            "error": "",
            "raw_status": "succeeded",
        }
        try:
            rows = asyncio.run(probe.query_seedance_statuses(candidates, "key", concurrency=1))
        finally:
            probe.query_seedance_task = original

        self.assertEqual(rows[0]["db"], "/data/users/user-a/database.db")
        self.assertEqual(rows[0]["local_status"], "processing")
        self.assertEqual(rows[0]["local_updated_at"], "2026-05-01T00:00:00Z")
        self.assertEqual(rows[0]["provider_video_url"], "https://example.com/video.mp4")

    def test_query_wan_statuses_preserves_repair_evidence(self):
        probe = load_task_state_probe_module()
        candidates = [{
            "db": "/data/users/user-a/database.db",
            "task_id": "local-1",
            "external_task_id": "external-1",
            "user_id": "user-a",
            "username": "alice",
            "display_name": "Alice",
            "team": "creative",
            "project_id": "project-1",
            "project_name": "Demo",
            "provider": "wan",
            "model": "wan2.2-animate-mix",
            "updated_at": "2026-05-01T00:00:00Z",
            "created_at": "2026-05-01T00:00:00Z",
        }]

        original = probe.query_wan_task
        probe.query_wan_task = lambda _api_key, _task_id: {
            "status": "completed",
            "video_url": "https://example.com/wan.mp4",
            "error": "",
            "raw_status": "SUCCEEDED",
        }
        try:
            rows = asyncio.run(probe.query_wan_statuses(candidates, "key", concurrency=1))
        finally:
            probe.query_wan_task = original

        self.assertEqual(rows[0]["provider"], "wan")
        self.assertEqual(rows[0]["local_updated_at"], "2026-05-01T00:00:00Z")
        self.assertEqual(rows[0]["provider_video_url"], "https://example.com/wan.mp4")

    def test_query_happyhorse_statuses_preserves_repair_evidence(self):
        probe = load_task_state_probe_module()
        candidates = [{
            "db": "/data/users/user-a/database.db",
            "task_id": "local-1",
            "external_task_id": "external-1",
            "user_id": "user-a",
            "username": "alice",
            "display_name": "Alice",
            "team": "creative",
            "project_id": "project-1",
            "project_name": "Demo",
            "provider": "happyhorse",
            "model": "happyhorse-1.0-r2v",
            "updated_at": "2026-05-01T00:00:00Z",
            "created_at": "2026-05-01T00:00:00Z",
        }]

        original = probe.query_wan_task
        probe.query_wan_task = lambda _api_key, _task_id: {
            "status": "completed",
            "video_url": "https://example.com/happyhorse.mp4",
            "error": "",
            "raw_status": "SUCCEEDED",
        }
        try:
            rows = asyncio.run(probe.query_happyhorse_statuses(candidates, "key", concurrency=1))
        finally:
            probe.query_wan_task = original

        self.assertEqual(rows[0]["provider"], "happyhorse")
        self.assertEqual(rows[0]["local_updated_at"], "2026-05-01T00:00:00Z")
        self.assertEqual(rows[0]["provider_video_url"], "https://example.com/happyhorse.mp4")


if __name__ == "__main__":
    unittest.main()
