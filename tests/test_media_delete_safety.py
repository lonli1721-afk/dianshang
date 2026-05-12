from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_USER_DATA_DIR = os.environ.get("USER_DATA_DIR")
_MODULE_USER_DATA_DIR = tempfile.mkdtemp(prefix="game-video-media-delete-module-")
os.environ["USER_DATA_DIR"] = _MODULE_USER_DATA_DIR
sys.path.insert(0, str(ROOT / "server"))

import database as db  # noqa: E402
import deps  # noqa: E402
import game_media_service  # noqa: E402
from routers import game_routes  # noqa: E402


class GameMediaServiceBoundaryTests(unittest.TestCase):
    def test_service_does_not_import_large_game_router(self):
        service_source = Path(game_media_service.__file__).read_text(encoding="utf-8")

        self.assertNotIn("routers.game_routes", service_source)
        self.assertNotIn("from routers import game_routes", service_source)
        self.assertNotIn("import game_routes", service_source)

    def test_delete_route_is_thin_service_wrapper(self):
        app = FastAPI()
        app.include_router(game_routes.router)
        client = TestClient(app)
        calls: list[tuple[set[str], str]] = []

        def fake_delete(urls: set[str], exclude_project_id: str = "") -> dict:
            calls.append((urls, exclude_project_id))
            return {"deleted": ["ok.mp4"], "skipped": [], "missing": []}

        original = game_routes._delete_local_files
        try:
            game_routes._delete_local_files = fake_delete
            response = client.post("/files/delete", json={
                "urls": ["/api/files/ok.mp4"],
                "project_id": "project-1",
            })
        finally:
            game_routes._delete_local_files = original

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cleanup"]["deleted"], ["ok.mp4"])
        self.assertEqual(calls, [({"/api/files/ok.mp4"}, "project-1")])


class MediaDeleteSafetyTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        if _ORIGINAL_USER_DATA_DIR is None:
            os.environ.pop("USER_DATA_DIR", None)
        else:
            os.environ["USER_DATA_DIR"] = _ORIGINAL_USER_DATA_DIR

    def setUp(self):
        self._old_db_path = db.get_db_path()
        self._old_files_dir = deps.get_files_dir()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="game-video-media-delete-"))
        db.set_db_path(self.temp_dir / "game_video.db")
        deps.set_files_dir(self.temp_dir / "files")

        app = FastAPI()
        app.include_router(game_routes.router)
        self.client = TestClient(app)

    def tearDown(self):
        db.set_db_path(self._old_db_path)
        deps.set_files_dir(self._old_files_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _file(self, name: str) -> Path:
        path = deps.get_files_dir() / name
        path.write_bytes(b"media")
        return path

    def _project(self, name: str = "Demo") -> dict:
        return db.create_game_project(name)

    def test_delete_skips_file_still_referenced_by_same_project_scenes(self):
        project = self._project()
        media = self._file("scene-video.mp4")
        db.update_game_project(project["id"], scenes_json=json.dumps({
            "generate": [{"id": "scene-1", "videoUrl": "/api/files/scene-video.mp4"}],
            "replace": [],
        }))

        response = self.client.post("/files/delete", json={
            "urls": ["/api/files/scene-video.mp4"],
            "project_id": project["id"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(media.exists())
        cleanup = response.json()["cleanup"]
        self.assertEqual(cleanup["deleted"], [])
        self.assertIn("scene-video.mp4", cleanup["skipped"])

    def test_delete_skips_file_still_referenced_by_same_project_asset(self):
        project = self._project()
        media = self._file("asset.png")
        db.create_game_asset(project["id"], "character", "Hero", image_url="/api/files/asset.png")

        response = self.client.post("/files/delete", json={
            "urls": ["/api/files/asset.png"],
            "project_id": project["id"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(media.exists())
        cleanup = response.json()["cleanup"]
        self.assertEqual(cleanup["deleted"], [])
        self.assertIn("asset.png", cleanup["skipped"])

    def test_same_project_task_reference_does_not_block_user_media_delete(self):
        project = self._project()
        media = self._file("task-only.mp4")
        task = db.create_game_task(project["id"], "generate", prompt="demo")
        db.update_game_task(task["id"], status="completed", video_url="/api/files/task-only.mp4")

        response = self.client.post("/files/delete", json={
            "urls": ["/api/files/task-only.mp4"],
            "project_id": project["id"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(media.exists())
        cleanup = response.json()["cleanup"]
        self.assertIn("task-only.mp4", cleanup["deleted"])
        self.assertEqual(cleanup["skipped"], [])

    def test_delete_without_project_id_uses_global_reference_protection(self):
        project = self._project()
        media = self._file("global-protected.mp4")
        db.update_game_project(project["id"], scenes_json=json.dumps({
            "generate": [{"id": "scene-1", "videoUrl": "/api/files/global-protected.mp4"}],
        }))

        response = self.client.post("/files/delete", json={
            "urls": ["/api/files/global-protected.mp4"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(media.exists())
        cleanup = response.json()["cleanup"]
        self.assertEqual(cleanup["deleted"], [])
        self.assertIn("global-protected.mp4", cleanup["skipped"])

    def test_delete_without_project_id_allows_unreferenced_temp_file(self):
        media = self._file("temp-upload.mp4")

        response = self.client.post("/files/delete", json={
            "urls": ["/api/files/temp-upload.mp4"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(media.exists())
        cleanup = response.json()["cleanup"]
        self.assertIn("temp-upload.mp4", cleanup["deleted"])
        self.assertEqual(cleanup["skipped"], [])

    def test_delete_skips_file_referenced_by_other_project(self):
        project = self._project("Owner")
        other = self._project("Other")
        media = self._file("shared.mp4")
        db.update_game_project(other["id"], scenes_json=json.dumps({
            "generate": [{"id": "scene-2", "videoUrl": "/api/files/shared.mp4"}],
        }))

        response = self.client.post("/files/delete", json={
            "urls": ["/api/files/shared.mp4"],
            "project_id": project["id"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(media.exists())
        cleanup = response.json()["cleanup"]
        self.assertEqual(cleanup["deleted"], [])
        self.assertIn("shared.mp4", cleanup["skipped"])

    def test_reference_matching_uses_exact_filename_not_like_wildcards(self):
        project = self._project("Owner")
        other = self._project("Other")
        media = self._file("clip_1.mp4")
        db.update_game_project(other["id"], scenes_json=json.dumps({
            "generate": [{"id": "scene-2", "videoUrl": "/api/files/clipX1.mp4"}],
        }))

        response = self.client.post("/files/delete", json={
            "urls": ["/api/files/clip_1.mp4"],
            "project_id": project["id"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(media.exists())
        cleanup = response.json()["cleanup"]
        self.assertIn("clip_1.mp4", cleanup["deleted"])
        self.assertEqual(cleanup["skipped"], [])

    def test_delete_skips_path_escape_and_directory_targets(self):
        directory = deps.get_files_dir() / "folder.mp4"
        directory.mkdir(parents=True)
        media = self._file("danger.mp4")

        response = self.client.post("/files/delete", json={
            "urls": ["/api/files/../danger.mp4", "/api/files/folder.mp4"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(media.exists())
        self.assertTrue(directory.exists())
        cleanup = response.json()["cleanup"]
        self.assertEqual(cleanup["deleted"], [])
        self.assertIn("/api/files/../danger.mp4", cleanup["skipped"])
        self.assertIn("folder.mp4", cleanup["skipped"])

    def test_delete_project_cleanup_is_not_blocked_by_deleted_project_state(self):
        project = self._project()
        media = self._file("project-owned.mp4")
        db.update_game_project(project["id"], scenes_json=json.dumps({
            "generate": [{"id": "scene-1", "videoUrl": "/api/files/project-owned.mp4"}],
        }))
        db.create_game_asset(project["id"], "scene", "Shot", image_url="/api/files/project-owned.mp4")

        response = self.client.delete(f"/projects/{project['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(media.exists())
        cleanup = response.json()["cleanup"]
        self.assertIn("project-owned.mp4", cleanup["deleted"])

    def test_upload_video_returns_duration_and_upload_image_skips_duration_lookup(self):
        duration_calls: list[str] = []

        def fake_duration(url: str) -> float:
            duration_calls.append(url)
            return 12.5

        original = game_routes.deps.get_local_video_duration_seconds
        try:
            game_routes.deps.get_local_video_duration_seconds = fake_duration
            video_response = self.client.post(
                "/upload",
                files={"file": ("clip.mp4", b"not-a-real-video", "video/mp4")},
            )
            image_response = self.client.post(
                "/upload",
                files={"file": ("image.png", b"png", "image/png")},
            )
        finally:
            game_routes.deps.get_local_video_duration_seconds = original

        self.assertEqual(video_response.status_code, 200)
        video_payload = video_response.json()
        self.assertEqual(video_payload["duration_seconds"], 12.5)
        self.assertTrue(video_payload["url"].startswith("/api/files/game_"))
        self.assertTrue(video_payload["filename"].endswith(".mp4"))
        self.assertEqual(video_payload["size"], len(b"not-a-real-video"))

        self.assertEqual(image_response.status_code, 200)
        image_payload = image_response.json()
        self.assertIsNone(image_payload["duration_seconds"])
        self.assertTrue(image_payload["filename"].endswith(".png"))
        self.assertEqual(len(duration_calls), 1)

    def test_media_info_uses_duration_lookup(self):
        calls: list[str] = []

        def fake_duration(url: str) -> float:
            calls.append(url)
            return 7.25

        original = game_routes.deps.get_local_video_duration_seconds
        try:
            game_routes.deps.get_local_video_duration_seconds = fake_duration
            response = self.client.post("/media_info", json={"url": "/api/files/a.mp4"})
        finally:
            game_routes.deps.get_local_video_duration_seconds = original

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"duration_seconds": 7.25})
        self.assertEqual(calls, ["/api/files/a.mp4"])


if __name__ == "__main__":
    unittest.main()
