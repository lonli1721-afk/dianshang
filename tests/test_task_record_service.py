from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_USER_DATA_DIR = os.environ.get("USER_DATA_DIR")
_MODULE_USER_DATA_DIR = tempfile.mkdtemp(prefix="game-video-task-record-service-module-")
os.environ["USER_DATA_DIR"] = _MODULE_USER_DATA_DIR
sys.path.insert(0, str(ROOT / "server"))

import database as db  # noqa: E402
import task_record_service  # noqa: E402
from routers import game_routes  # noqa: E402


class TaskRecordServiceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(_MODULE_USER_DATA_DIR, ignore_errors=True)
        if _ORIGINAL_USER_DATA_DIR is None:
            os.environ.pop("USER_DATA_DIR", None)
        else:
            os.environ["USER_DATA_DIR"] = _ORIGINAL_USER_DATA_DIR

    def test_service_does_not_import_large_game_router(self):
        service_source = Path(task_record_service.__file__).read_text(encoding="utf-8")

        self.assertNotIn("routers.game_routes", service_source)
        self.assertNotIn("from routers import game_routes", service_source)
        self.assertNotIn("import game_routes", service_source)

    def test_success_persists_record_and_clears_retry_payload(self):
        calls = []
        video_tasks = {
            "task-1": {
                "provider": "jimeng",
                "task_record_payload": {"project_id": "project-1"},
            }
        }
        payload = {
            "project_id": "project-1",
            "type_": "generate",
            "prompt": "demo",
            "model": "seedance-2.0",
            "provider": "jimeng",
        }

        async def fake_db_call(fn, *args, **kwargs):
            calls.append((fn, args, kwargs))
            return {"id": "local-task-1"}

        warning = asyncio.run(task_record_service.ensure_game_task_record(
            "task-1",
            payload,
            db_call=fake_db_call,
            video_tasks=video_tasks,
        ))

        self.assertEqual(warning, "")
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], db.create_game_task)
        self.assertEqual(calls[0][2]["external_task_id"], "task-1")
        self.assertNotIn("task_record_payload", video_tasks["task-1"])

    def test_missing_project_id_is_noop(self):
        calls = []

        async def fake_db_call(*args, **kwargs):
            calls.append((args, kwargs))

        warning = asyncio.run(task_record_service.ensure_game_task_record(
            "task-1",
            {"prompt": "demo"},
            db_call=fake_db_call,
            video_tasks={},
        ))

        self.assertEqual(warning, "")
        self.assertEqual(calls, [])

    def test_generate_payload_matches_existing_route_shape(self):
        payload = task_record_service.build_generate_task_record_payload(
            project_id="project-1",
            prompt="demo",
            model="seedance-2.0",
            provider="jimeng",
            character_refs=["/api/files/char.png"],
            scene_refs=["/api/files/scene.png"],
            reference_video_url="/api/files/ref.mp4",
            advanced_reference_videos=[],
        )

        self.assertEqual(payload, {
            "project_id": "project-1",
            "type_": "generate",
            "prompt": "demo",
            "model": "seedance-2.0",
            "provider": "jimeng",
            "character_refs": ["/api/files/char.png"],
            "scene_refs": ["/api/files/scene.png"],
            "ref_video_path": "/api/files/ref.mp4",
        })

    def test_generate_payload_serializes_advanced_reference_videos(self):
        payload = task_record_service.build_generate_task_record_payload(
            project_id="project-1",
            prompt="demo",
            model="happyhorse-1.0-video-edit",
            provider="happyhorse",
            reference_video_url="/api/files/ref.mp4",
            advanced_reference_videos=["/api/files/甲.mp4", "/api/files/乙.mp4"],
        )

        self.assertEqual(payload["ref_video_path"], '["/api/files/甲.mp4", "/api/files/乙.mp4"]')

    def test_replace_payload_matches_existing_route_shape(self):
        payload = task_record_service.build_replace_task_record_payload(
            project_id="project-1",
            prompt="Seedance 动作模仿",
            model="seedance-2.0",
            provider="jimeng",
            character_ref="/api/files/char.png",
            ref_video_url="/api/files/ref.mp4",
        )

        self.assertEqual(payload, {
            "project_id": "project-1",
            "type_": "replace",
            "prompt": "Seedance 动作模仿",
            "model": "seedance-2.0",
            "provider": "jimeng",
            "character_refs": ["/api/files/char.png"],
            "scene_refs": [],
            "ref_video_path": "/api/files/ref.mp4",
        })

    def test_failure_keeps_payload_for_later_status_retry(self):
        video_tasks = {"task-1": {"provider": "jimeng"}}
        payload = {"project_id": "project-1", "type_": "generate"}

        async def fake_db_call(*_args, **_kwargs):
            raise RuntimeError("database locked")

        warning = asyncio.run(task_record_service.ensure_game_task_record(
            "task-1",
            payload,
            db_call=fake_db_call,
            video_tasks=video_tasks,
        ))

        self.assertIn("本地任务记录保存失败", warning)
        self.assertIs(video_tasks["task-1"]["task_record_payload"], payload)

    def test_router_ensure_task_record_is_thin_service_wrapper(self):
        async def fake_service(task_id: str, payload: dict, **kwargs) -> str:
            self.assertEqual(task_id, "task-1")
            self.assertEqual(payload["project_id"], "project-1")
            self.assertIs(kwargs["db_call"], game_routes._db_call)
            self.assertIs(kwargs["video_tasks"], game_routes.deps._video_tasks)
            self.assertIs(kwargs["logger"], game_routes.logger)
            return "warning"

        with patch.object(game_routes, "ensure_game_task_record_service", fake_service):
            result = asyncio.run(game_routes._ensure_game_task_record("task-1", {"project_id": "project-1"}))

        self.assertEqual(result, "warning")


if __name__ == "__main__":
    unittest.main()
