from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_preflight_module():
    spec = importlib.util.spec_from_file_location("media_cleanup_preflight", ROOT / "deploy" / "media-cleanup-preflight.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_cleanup_plan_module():
    spec = importlib.util.spec_from_file_location("media_cleanup_plan", ROOT / "deploy" / "media-cleanup-plan.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_args(allowlist: Path, data_dir: Path, **overrides):
    values = {
        "allowlist": allowlist,
        "data_dir": data_dir,
        "json_report": None,
        "min_age_hours": 24.0,
        "include_all_tables": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def plan_args(data_dir: Path):
    return SimpleNamespace(
        data_dir=data_dir,
        json_report=None,
        min_age_hours=24.0,
        candidate_limit=0,
        sample_limit=50,
        reference_sample_limit=3,
        include_all_tables=False,
    )


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


def write_old_file(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    ts = time.time() - 72 * 3600
    os.utime(path, (ts, ts))
    return path


def write_allowlist(path: Path, rows: list[dict], **overrides) -> Path:
    payload = {
        "action": "media_cleanup_allowlist",
        "dry_run": True,
        "deletion_enabled": False,
        "review_required": True,
        "created_at": "2026-05-05T00:00:00+08:00",
        "selection": {
            "min_age_hours": 24.0,
            "max_count": 20,
            "max_bytes": 512 * 1024 * 1024,
            "sort": "size-desc",
            "fill_gaps": False,
            "scope": ["global", "user"],
        },
        "preflight_errors": [],
        "selected_count": len(rows),
        "selected_logical_bytes": sum(int(row.get("size") or 0) for row in rows),
        "allowlist": rows,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def allowlist_row_from_candidate(candidate: dict, review_status: str = "approved") -> dict:
    return {
        "candidate_id": candidate["candidate_id"],
        "path": candidate["path"],
        "filename": candidate.get("filename", ""),
        "scope": candidate.get("scope", ""),
        "user_id": candidate.get("user_id", ""),
        "size": candidate["size"],
        "mtime": candidate["mtime"],
        "age_hours": candidate["age_hours"],
        "reference_count": candidate["reference_count"],
        "reference_kinds": candidate.get("reference_kinds") or {},
        "expected": {
            "size": candidate["size"],
            "mtime": candidate["mtime"],
            "reference_class": "unreferenced",
            "path": candidate["path"],
        },
        "review_status": review_status,
    }


class MediaCleanupPreflightTests(unittest.TestCase):
    def test_preflight_verifies_approved_allowlist_against_current_plan(self):
        preflight = load_preflight_module()
        cleanup_plan = load_cleanup_plan_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_old_file(data_dir / "files" / "orphan.mp4", b"orphan")
            plan = cleanup_plan.build_plan(plan_args(data_dir))
            allowlist = write_allowlist(
                data_dir / "allowlist.json",
                [allowlist_row_from_candidate(plan["candidates"][0], review_status="approved")],
            )

            payload = preflight.build_preflight(make_args(allowlist, data_dir))

        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["deletion_enabled"])
        self.assertTrue(payload["technically_verified"])
        self.assertTrue(payload["ready_for_execution"])
        self.assertFalse(payload["human_review_required"])
        self.assertEqual(payload["verified_count"], 1)
        self.assertEqual(payload["blocked_count"], 0)

    def test_pending_review_is_not_ready_for_execution(self):
        preflight = load_preflight_module()
        cleanup_plan = load_cleanup_plan_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_old_file(data_dir / "files" / "orphan.mp4", b"orphan")
            plan = cleanup_plan.build_plan(plan_args(data_dir))
            allowlist = write_allowlist(
                data_dir / "allowlist.json",
                [allowlist_row_from_candidate(plan["candidates"][0], review_status="pending")],
            )

            payload = preflight.build_preflight(make_args(allowlist, data_dir))

        self.assertTrue(payload["technically_verified"])
        self.assertFalse(payload["ready_for_execution"])
        self.assertTrue(payload["human_review_required"])
        self.assertEqual(payload["pending_review_count"], 1)

    def test_size_or_mtime_change_blocks_candidate(self):
        preflight = load_preflight_module()
        cleanup_plan = load_cleanup_plan_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            media = write_old_file(data_dir / "files" / "orphan.mp4", b"orphan")
            plan = cleanup_plan.build_plan(plan_args(data_dir))
            allowlist = write_allowlist(
                data_dir / "allowlist.json",
                [allowlist_row_from_candidate(plan["candidates"][0], review_status="approved")],
            )
            media.write_bytes(b"orphan changed")
            ts = time.time() - 72 * 3600
            os.utime(media, (ts, ts))

            payload = preflight.build_preflight(make_args(allowlist, data_dir))

        self.assertFalse(payload["technically_verified"])
        self.assertFalse(payload["ready_for_execution"])
        self.assertEqual(payload["blocked_count"], 1)
        reasons = payload["items"][0]["reasons"]
        self.assertIn("candidate_id_changed", reasons)
        self.assertIn("size_changed", reasons)

    def test_new_reference_blocks_candidate(self):
        preflight = load_preflight_module()
        cleanup_plan = load_cleanup_plan_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_old_file(data_dir / "files" / "orphan.mp4", b"orphan")
            plan = cleanup_plan.build_plan(plan_args(data_dir))
            allowlist = write_allowlist(
                data_dir / "allowlist.json",
                [allowlist_row_from_candidate(plan["candidates"][0], review_status="approved")],
            )
            db_path = data_dir / "users" / "user-a" / "database.db"
            create_project_db(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO game_projects (id, scenes_json) VALUES (?,?)",
                ("project-a", '{"videoUrl": "/api/files/orphan.mp4"}'),
            )
            conn.commit()
            conn.close()

            payload = preflight.build_preflight(make_args(allowlist, data_dir))

        self.assertFalse(payload["technically_verified"])
        self.assertEqual(payload["blocked_count"], 1)
        self.assertIn("not_in_current_cleanup_plan", payload["items"][0]["reasons"])

    def test_allowlist_header_errors_block_preflight(self):
        preflight = load_preflight_module()
        cleanup_plan = load_cleanup_plan_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_old_file(data_dir / "files" / "orphan.mp4", b"orphan")
            plan = cleanup_plan.build_plan(plan_args(data_dir))
            allowlist = write_allowlist(
                data_dir / "allowlist.json",
                [allowlist_row_from_candidate(plan["candidates"][0], review_status="approved")],
                deletion_enabled=True,
            )

            payload = preflight.build_preflight(make_args(allowlist, data_dir))

        self.assertFalse(payload["technically_verified"])
        self.assertIn("allowlist_deletion_must_be_disabled", payload["preflight_errors"])

    def test_json_report_does_not_modify_allowlist(self):
        preflight = load_preflight_module()
        cleanup_plan = load_cleanup_plan_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_old_file(data_dir / "files" / "orphan.mp4", b"orphan")
            plan = cleanup_plan.build_plan(plan_args(data_dir))
            allowlist = write_allowlist(
                data_dir / "allowlist.json",
                [allowlist_row_from_candidate(plan["candidates"][0], review_status="approved")],
            )
            before = allowlist.read_text(encoding="utf-8")
            out = data_dir / "preflight.json"

            payload = preflight.build_preflight(make_args(allowlist, data_dir, json_report=out))
            preflight.write_json_report(out, payload)

            self.assertEqual(allowlist.read_text(encoding="utf-8"), before)
            written = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(written["action"], "media_cleanup_preflight")

    def test_script_has_no_execute_or_delete_primitives(self):
        source = (ROOT / "deploy" / "media-cleanup-preflight.py").read_text(encoding="utf-8")

        self.assertNotIn("--execute", source)
        self.assertNotIn(".unlink(", source)
        self.assertNotIn("rmtree(", source)
        self.assertNotIn("os.remove", source)
        self.assertNotIn("os.replace", source)
        self.assertNotIn("os.link", source)
        self.assertNotIn("DELETE FROM", source)
        self.assertNotIn("UPDATE ", source)
        self.assertNotIn("INSERT INTO", source)
        self.assertNotIn("CREATE TABLE", source)
        self.assertNotIn("DROP TABLE", source)


if __name__ == "__main__":
    unittest.main()
