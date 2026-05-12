from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_USER_DATA_DIR = os.environ.get("USER_DATA_DIR")
_MODULE_USER_DATA_DIR = tempfile.mkdtemp(prefix="viral-media-service-module-")
os.environ["USER_DATA_DIR"] = _MODULE_USER_DATA_DIR
sys.path.insert(0, str(ROOT / "server"))

import database as db  # noqa: E402
import deps  # noqa: E402
import viral_media_service  # noqa: E402
from routers import viral_routes  # noqa: E402


class ViralMediaServiceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self._old_db_path = db.get_db_path()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="viral-media-boundary-"))
        db.set_db_path(self.temp_dir / "game_video.db")

    def tearDown(self):
        db.set_db_path(self._old_db_path)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_service_does_not_import_large_viral_router(self):
        service_source = Path(viral_media_service.__file__).read_text(encoding="utf-8")

        self.assertNotIn("routers.viral_routes", service_source)
        self.assertNotIn("from routers import viral_routes", service_source)
        self.assertNotIn("import viral_routes", service_source)

    def test_delete_route_is_thin_service_wrapper(self):
        app = FastAPI()
        app.include_router(viral_routes.router)
        client = TestClient(app)
        video = db.create_viral_video(
            user_id="",
            source_name="clip.mp4",
            file_url="/api/files/viral-route.mp4",
            file_size=10,
            duration_seconds=1.0,
        )
        calls: list[tuple[str, str]] = []

        def fake_delete(file_url: str, user_id: str = "") -> dict:
            calls.append((file_url, user_id))
            return {"deleted": ["viral-route.mp4"], "skipped": [], "missing": []}

        original = viral_routes.safe_delete_local_file_if_unreferenced
        try:
            viral_routes.safe_delete_local_file_if_unreferenced = fake_delete
            response = client.delete(f"/videos/{video['id']}")
        finally:
            viral_routes.safe_delete_local_file_if_unreferenced = original

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cleanup"]["deleted"], ["viral-route.mp4"])
        self.assertEqual(calls, [("/api/files/viral-route.mp4", "")])


class ViralMediaServiceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        if _ORIGINAL_USER_DATA_DIR is None:
            os.environ.pop("USER_DATA_DIR", None)
        else:
            os.environ["USER_DATA_DIR"] = _ORIGINAL_USER_DATA_DIR
        shutil.rmtree(_MODULE_USER_DATA_DIR, ignore_errors=True)

    def setUp(self):
        self._old_db_path = db.get_db_path()
        self._old_files_dir = deps.get_files_dir()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="viral-media-service-"))
        db.set_db_path(self.temp_dir / "game_video.db")
        deps.set_files_dir(self.temp_dir / "files")

    def tearDown(self):
        db.set_db_path(self._old_db_path)
        deps.set_files_dir(self._old_files_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_file(self, name: str, content: bytes = b"video") -> Path:
        path = deps.get_files_dir() / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_unreferenced_viral_file_deletes(self):
        path = self._write_file("orphan.mp4")

        cleanup = viral_media_service.safe_delete_local_file_if_unreferenced("/api/files/orphan.mp4", "user-a")

        self.assertEqual(cleanup["deleted"], ["orphan.mp4"])
        self.assertFalse(path.exists())

    def test_analysis_reference_protects_file_after_video_row_deleted(self):
        path = self._write_file("analysis-ref.mp4")
        video = db.create_viral_video(
            user_id="user-a",
            source_name="clip.mp4",
            file_url="/api/files/analysis-ref.mp4",
            file_size=10,
            duration_seconds=1.0,
        )
        db.create_viral_analysis(user_id="user-a", video_ids=[video["id"]], video_urls=["/api/files/analysis-ref.mp4"])
        db.delete_viral_video(video["id"], user_id="user-a")

        cleanup = viral_media_service.safe_delete_local_file_if_unreferenced("/api/files/analysis-ref.mp4", "user-a")

        self.assertEqual(cleanup["skipped"], ["/api/files/analysis-ref.mp4"])
        self.assertTrue(path.exists())

    def test_other_user_reference_protects_shared_viral_file(self):
        path = self._write_file("shared-viral.mp4")
        user_a_video = db.create_viral_video(
            user_id="user-a",
            source_name="clip-a.mp4",
            file_url="/api/files/shared-viral.mp4",
            file_size=10,
            duration_seconds=1.0,
        )
        db.create_viral_video(
            user_id="user-b",
            source_name="clip-b.mp4",
            file_url="/api/files/shared-viral.mp4",
            file_size=10,
            duration_seconds=1.0,
        )
        db.delete_viral_video(user_a_video["id"], user_id="user-a")

        cleanup = viral_media_service.safe_delete_local_file_if_unreferenced("/api/files/shared-viral.mp4", "user-a")

        self.assertEqual(cleanup["skipped"], ["/api/files/shared-viral.mp4"])
        self.assertTrue(path.exists())

    def test_path_escape_and_directory_are_skipped(self):
        directory = deps.get_files_dir() / "folder.mp4"
        directory.mkdir(parents=True)

        escape_cleanup = viral_media_service.safe_delete_local_file_if_unreferenced("/api/files/../danger.mp4", "user-a")
        directory_cleanup = viral_media_service.safe_delete_local_file_if_unreferenced("/api/files/folder.mp4", "user-a")

        self.assertIn("/api/files/../danger.mp4", escape_cleanup["missing"])
        self.assertEqual(directory_cleanup["skipped"], ["folder.mp4"])
        self.assertTrue(directory.exists())

    def test_save_viral_upload_persists_record_and_duration(self):
        async def fake_write(_file, target_path: Path):
            target_path.write_bytes(b"video")
            return 5

        fake_file = SimpleNamespace(filename="素材.mp4")
        with patch.object(viral_media_service.deps, "write_upload_to_path", side_effect=fake_write), \
             patch.object(viral_media_service.deps, "notify_media_file_saved") as notify_saved, \
             patch.object(viral_media_service.deps, "get_local_video_duration_seconds", return_value=8.5):
            record = asyncio.run(viral_media_service.save_viral_upload(fake_file, user_id="user-a"))

        self.assertEqual(record["user_id"], "user-a")
        self.assertEqual(record["source_name"], "素材.mp4")
        self.assertEqual(record["file_size"], 5)
        self.assertEqual(record["duration_seconds"], 8.5)
        self.assertTrue(record["file_url"].startswith("/api/files/viral_"))
        notify_saved.assert_called_once()

    def test_oversized_upload_removes_temp_file(self):
        async def fake_write(_file, target_path: Path):
            target_path.write_bytes(b"too-large")
            return 11

        fake_file = SimpleNamespace(filename="clip.mp4")
        old_limit = viral_media_service.MAX_VIRAL_UPLOAD_BYTES
        viral_media_service.MAX_VIRAL_UPLOAD_BYTES = 10
        try:
            with patch.object(viral_media_service.deps, "write_upload_to_path", side_effect=fake_write):
                with self.assertRaisesRegex(Exception, "单个视频不能超过"):
                    asyncio.run(viral_media_service.save_viral_upload(fake_file, user_id="user-a"))
        finally:
            viral_media_service.MAX_VIRAL_UPLOAD_BYTES = old_limit

        self.assertEqual(list(deps.get_files_dir().glob("viral_*.mp4")), [])
