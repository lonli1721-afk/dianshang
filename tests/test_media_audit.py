from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_media_audit_module():
    spec = importlib.util.spec_from_file_location("media_audit", ROOT / "deploy" / "media-audit.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_args(data_dir: Path, **overrides):
    values = {
        "data_dir": data_dir,
        "json_report": None,
        "verify_hash": True,
        "hash_limit": 0,
        "sample_limit": 50,
        "reference_sample_limit": 5,
        "include_all_tables": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def create_project_db(path: Path, extra_sql: str = "") -> None:
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
    if extra_sql:
        conn.executescript(extra_sql)
    conn.commit()
    conn.close()


class MediaAuditTests(unittest.TestCase):
    def test_build_report_classifies_active_task_only_and_unreferenced_media(self):
        media_audit = load_media_audit_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            global_files = data_dir / "files"
            user_files = data_dir / "users" / "user-a" / "files"
            global_files.mkdir(parents=True)
            user_files.mkdir(parents=True)
            (global_files / "active.mp4").write_bytes(b"same")
            (user_files / "active.mp4").write_bytes(b"same")
            (global_files / "task-only.mp4").write_bytes(b"task")
            (global_files / "orphan.png").write_bytes(b"orphan")

            db_path = data_dir / "users" / "user-a" / "database.db"
            create_project_db(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO game_projects (id, scenes_json) VALUES (?,?)",
                ("project-a", '{"videoUrl": "/api/files/active.mp4"}'),
            )
            conn.execute(
                "INSERT INTO game_tasks (id, project_id, video_url) VALUES (?,?,?)",
                ("task-a", "project-a", "/api/files/task-only.mp4"),
            )
            conn.commit()
            conn.close()

            payload = media_audit.build_report(make_args(data_dir))

        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["pair_count"], 1)
        self.assertEqual(payload["media_lifecycle"]["local_file_count"], 4)
        self.assertEqual(payload["media_lifecycle"]["reference_matching_scope"], "filename_basename")
        self.assertEqual(payload["media_lifecycle"]["active_state_referenced_filename_count"], 1)
        self.assertEqual(payload["media_lifecycle"]["task_only_referenced_filename_count"], 1)
        self.assertEqual(payload["media_lifecycle"]["suspected_unreferenced_filename_count"], 1)
        self.assertEqual(payload["media_lifecycle"]["suspected_unreferenced_file_count"], 1)
        self.assertEqual(payload["media_lifecycle"]["largest_unreferenced_sample"][0]["filename"], "orphan.png")
        self.assertFalse(payload["media_lifecycle"]["pending_delete_queue"]["persisted"])
        self.assertIn("basename", payload["media_lifecycle"]["limitations"][0])

    def test_reference_matching_uses_exact_filename(self):
        media_audit = load_media_audit_module()

        found = media_audit.extract_media_filenames(
            '"/api/files/clipX1.mp4"',
            {"clip_1.mp4"},
        )

        self.assertEqual(found, set())

    def test_scan_references_respects_default_tables_and_include_all_tables(self):
        media_audit = load_media_audit_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            db_path = data_dir / "game_video.db"
            create_project_db(
                db_path,
                """
                CREATE TABLE custom_notes (
                    id TEXT PRIMARY KEY,
                    body TEXT DEFAULT ''
                );
                """,
            )
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO game_tasks (id, video_url) VALUES (?,?)",
                ("task-a", "/api/files/demo.mp4"),
            )
            conn.execute(
                "INSERT INTO custom_notes (id, body) VALUES (?,?)",
                ("note-a", "/api/files/demo.mp4"),
            )
            conn.commit()
            conn.close()

            default_report = media_audit.scan_references(data_dir, {"demo.mp4"}, False, 5)
            all_report = media_audit.scan_references(data_dir, {"demo.mp4"}, True, 5)

        self.assertEqual(default_report["reference_counts"]["demo.mp4"], 1)
        self.assertEqual(all_report["reference_counts"]["demo.mp4"], 2)
        self.assertEqual(default_report["reference_counts_by_kind"]["demo.mp4"]["task_record"], 1)

    def test_build_report_does_not_modify_media_or_database(self):
        media_audit = load_media_audit_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            files_dir = data_dir / "files"
            files_dir.mkdir(parents=True)
            media_path = files_dir / "keep.mp4"
            media_path.write_bytes(b"keep")
            db_path = data_dir / "game_video.db"
            create_project_db(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO game_projects (id, scenes_json) VALUES (?,?)",
                ("project-a", '{"videoUrl": "/api/files/keep.mp4"}'),
            )
            conn.commit()
            conn.close()

            payload = media_audit.build_report(make_args(data_dir, verify_hash=False))

            self.assertEqual(media_path.read_bytes(), b"keep")
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT scenes_json FROM game_projects WHERE id=?", ("project-a",)).fetchone()
            conn.close()

        self.assertTrue(payload["dry_run"])
        self.assertIn("keep.mp4", row[0])


if __name__ == "__main__":
    unittest.main()
