from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_cleanup_plan_module():
    spec = importlib.util.spec_from_file_location("media_cleanup_plan", ROOT / "deploy" / "media-cleanup-plan.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_args(data_dir: Path, **overrides):
    values = {
        "data_dir": data_dir,
        "json_report": None,
        "min_age_hours": 24.0,
        "candidate_limit": 1000,
        "sample_limit": 50,
        "reference_sample_limit": 3,
        "include_all_tables": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def create_project_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE game_projects (
            id TEXT PRIMARY KEY,
            scenes_json TEXT DEFAULT ''
        );
        CREATE TABLE game_assets (
            id TEXT PRIMARY KEY,
            project_id TEXT DEFAULT '',
            image_url TEXT DEFAULT ''
        );
        CREATE TABLE game_tasks (
            id TEXT PRIMARY KEY,
            project_id TEXT DEFAULT '',
            character_refs TEXT DEFAULT '',
            scene_refs TEXT DEFAULT '',
            ref_video_path TEXT DEFAULT '',
            video_url TEXT DEFAULT ''
        );
        """
    )
    conn.commit()
    conn.close()


def write_file(path: Path, data: bytes, old: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if old:
        ts = time.time() - 72 * 3600
        os.utime(path, (ts, ts))
    return path


class MediaCleanupPlanTests(unittest.TestCase):
    def test_plan_only_candidates_old_unreferenced_media(self):
        cleanup_plan = load_cleanup_plan_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            files_dir = data_dir / "files"
            orphan = write_file(files_dir / "orphan.mp4", b"orphan")
            write_file(files_dir / "active.mp4", b"active")
            write_file(files_dir / "task-only.mp4", b"task")
            write_file(files_dir / "recent.png", b"recent", old=False)

            db_path = data_dir / "users" / "user-a" / "database.db"
            create_project_db(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO game_projects (id, scenes_json) VALUES (?,?)",
                ("project-a", '{"videoUrl": "/api/files/active.mp4"}'),
            )
            conn.execute(
                "INSERT INTO game_tasks (id, video_url) VALUES (?,?)",
                ("task-a", "/api/files/task-only.mp4"),
            )
            conn.commit()
            conn.close()

            payload = cleanup_plan.build_plan(make_args(data_dir))

        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["deletion_enabled"])
        self.assertEqual(payload["candidate_count"], 1)
        self.assertEqual(payload["candidates"][0]["path"], str(orphan))
        self.assertEqual(payload["candidates"][0]["recheck"]["reference_class"], "unreferenced")
        self.assertEqual(payload["skipped_by_reason"]["active_state_reference"], 1)
        self.assertEqual(payload["skipped_by_reason"]["task_only_reference"], 1)
        self.assertEqual(payload["skipped_by_reason"]["too_recent"], 1)

    def test_referenced_basename_protects_all_same_named_files(self):
        cleanup_plan = load_cleanup_plan_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_file(data_dir / "files" / "shared.mp4", b"global")
            write_file(data_dir / "users" / "user-a" / "files" / "shared.mp4", b"user")
            db_path = data_dir / "users" / "user-a" / "database.db"
            create_project_db(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO game_projects (id, scenes_json) VALUES (?,?)",
                ("project-a", '{"videoUrl": "/api/files/shared.mp4"}'),
            )
            conn.commit()
            conn.close()

            payload = cleanup_plan.build_plan(make_args(data_dir))

        self.assertEqual(payload["candidate_count"], 0)
        self.assertEqual(payload["skipped_by_reason"]["active_state_reference"], 2)
        self.assertEqual(payload["reference_matching_scope"], "filename_basename")

    def test_estimated_reclaim_counts_hardlinked_inode_once(self):
        cleanup_plan = load_cleanup_plan_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            global_path = write_file(data_dir / "files" / "dupe.mp4", b"duplicate")
            user_path = data_dir / "users" / "user-a" / "files" / "dupe.mp4"
            user_path.parent.mkdir(parents=True, exist_ok=True)
            os.link(global_path, user_path)
            ts = time.time() - 72 * 3600
            os.utime(global_path, (ts, ts))

            payload = cleanup_plan.build_plan(make_args(data_dir, candidate_limit=0))

        self.assertEqual(payload["candidate_count"], 2)
        self.assertEqual(payload["candidate_logical_bytes"], len(b"duplicate") * 2)
        self.assertEqual(payload["estimated_reclaim_bytes"], len(b"duplicate"))

    def test_build_plan_does_not_modify_media_or_database(self):
        cleanup_plan = load_cleanup_plan_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            media_path = write_file(data_dir / "files" / "keep.mp4", b"keep")
            db_path = data_dir / "game_video.db"
            create_project_db(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO game_projects (id, scenes_json) VALUES (?,?)",
                ("project-a", '{"videoUrl": "/api/files/keep.mp4"}'),
            )
            conn.commit()
            conn.close()

            payload = cleanup_plan.build_plan(make_args(data_dir))

            self.assertEqual(media_path.read_bytes(), b"keep")
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT scenes_json FROM game_projects WHERE id=?", ("project-a",)).fetchone()
            conn.close()

        self.assertIn("keep.mp4", row[0])
        self.assertEqual(payload["candidate_count"], 0)

    def test_script_has_no_execute_or_delete_primitives(self):
        source = (ROOT / "deploy" / "media-cleanup-plan.py").read_text(encoding="utf-8")

        self.assertNotIn("--execute", source)
        self.assertNotIn(".unlink(", source)
        self.assertNotIn("rmtree(", source)
        self.assertNotIn("os.remove", source)
        self.assertNotIn("DELETE FROM", source)
        self.assertNotIn("UPDATE ", source)


if __name__ == "__main__":
    unittest.main()
