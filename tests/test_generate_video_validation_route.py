from __future__ import annotations

import inspect
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_USER_DATA_DIR = os.environ.get("USER_DATA_DIR")
_TEMP_USER_DATA_DIR = tempfile.mkdtemp(prefix="game-video-route-validation-")
os.environ["USER_DATA_DIR"] = _TEMP_USER_DATA_DIR
sys.path.insert(0, str(ROOT / "server"))

from routers import game_routes  # noqa: E402


class FakeSeedanceService:
    def __init__(self):
        self.calls: list[dict] = []

    async def generate_video(self, **kwargs):
        self.calls.append(kwargs)
        return {"task_id": "fake-seedance-task", "status": "processing", "provider": "jimeng", "duration": kwargs["duration"]}


class FakeHappyHorseService:
    def __init__(self):
        self.calls: list[dict] = []

    async def reference_to_video(self, **kwargs):
        self.calls.append(kwargs)
        return {"task_id": "fake-happyhorse-task", "status": "processing", "provider": "happyhorse"}


async def _run_provider_call(provider, operation, fn):
    result = fn()
    if inspect.isawaitable(result):
        return await result
    return result


def _json_from_keepalive_response(response):
    return json.loads(response.text.strip())


class GenerateVideoValidationRouteTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TEMP_USER_DATA_DIR, ignore_errors=True)
        if _ORIGINAL_USER_DATA_DIR is None:
            os.environ.pop("USER_DATA_DIR", None)
        else:
            os.environ["USER_DATA_DIR"] = _ORIGINAL_USER_DATA_DIR

    def setUp(self):
        app = FastAPI()
        app.include_router(game_routes.router)
        self.client = TestClient(app)

    def test_validation_error_returns_400_before_provider_initialization(self):
        service_factory = Mock()
        with patch.object(game_routes, "_game_video_svc", service_factory):
            response = self.client.post(
                "/generate_video",
                json={
                    "prompt": "tiny smoke",
                    "provider": "jimeng",
                    "model": "seedance-2.0-fast",
                    "duration": 11,
                    "resolution": "720p",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("4-10 秒", response.text)
        service_factory.assert_not_called()

    def test_reference_video_is_rejected_for_seedance_15_before_provider_resolution(self):
        resolver = Mock()
        with patch.object(game_routes.deps, "resolve_video_as_public_url", resolver), \
                patch.object(game_routes, "_game_video_svc", Mock()):
            response = self.client.post(
                "/generate_video",
                json={
                    "prompt": "tiny smoke",
                    "provider": "jimeng",
                    "model": "seedance-1.5-pro",
                    "duration": 4,
                    "resolution": "720p",
                    "reference_video_url": "/api/files/ref.mp4",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("不支持参考视频", response.text)
        resolver.assert_not_called()

    def test_seedance_reference_video_duration_is_checked_before_provider_call(self):
        provider_call = Mock()
        with patch.object(game_routes, "_game_video_svc", Mock(return_value=object())), \
                patch.object(game_routes, "_provider_call", provider_call), \
                patch.object(game_routes.deps, "get_local_video_duration_seconds", Mock(return_value=16.0)):
            response = self.client.post(
                "/generate_video",
                json={
                    "prompt": "tiny smoke",
                    "provider": "jimeng",
                    "model": "seedance-2.0",
                    "duration": 4,
                    "resolution": "720p",
                    "reference_video_url": "/api/files/ref.mp4",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = _json_from_keepalive_response(response)
        self.assertIn("15.2 秒以内", body["_error"])
        provider_call.assert_not_called()

    def test_seedance_advanced_reference_total_duration_is_checked_before_provider_call(self):
        provider_call = Mock()

        def fake_duration(url):
            return {"/api/files/a.mp4": 8.0, "/api/files/b.mp4": 8.0}.get(url)

        with patch.object(game_routes, "_game_video_svc", Mock(return_value=object())), \
                patch.object(game_routes, "_provider_call", provider_call), \
                patch.object(game_routes.deps, "get_local_video_duration_seconds", Mock(side_effect=fake_duration)):
            response = self.client.post(
                "/generate_video",
                json={
                    "prompt": "tiny smoke",
                    "provider": "jimeng",
                    "model": "seedance-2.0",
                    "duration": 4,
                    "resolution": "720p",
                    "advanced_reference_videos": ["/api/files/a.mp4", "/api/files/b.mp4"],
                },
            )

        self.assertEqual(response.status_code, 200)
        body = _json_from_keepalive_response(response)
        self.assertIn("总时长", body["_error"])
        self.assertIn("15.2 秒以内", body["_error"])
        provider_call.assert_not_called()

    def test_seedance_scene_refs_are_not_mixed_with_first_frame_when_multiple_refs_exist(self):
        fake_service = FakeSeedanceService()

        async def fake_resolve(url, **_kwargs):
            return f"https://files.example/{url.rsplit('/', 1)[-1]}"

        async def fake_ensure_task_record(*_args, **_kwargs):
            return None

        with patch.object(game_routes, "_game_video_svc", return_value=fake_service), \
                patch.object(game_routes.deps, "resolve_image_for_external", fake_resolve), \
                patch.object(game_routes, "_provider_call", _run_provider_call), \
                patch.object(game_routes, "_ensure_game_task_record", fake_ensure_task_record):
            response = self.client.post(
                "/generate_video",
                json={
                    "prompt": "tiny smoke",
                    "provider": "jimeng",
                    "model": "seedance-2.0",
                    "duration": 4,
                    "resolution": "720p",
                    "scene_refs": ["/api/files/a.png", "/api/files/b.png"],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_json_from_keepalive_response(response)["task_id"], "fake-seedance-task")
        self.assertEqual(fake_service.calls[0]["image_url"], "")
        self.assertEqual(
            fake_service.calls[0]["reference_images"],
            ["https://files.example/a.png", "https://files.example/b.png"],
        )

    def test_seedance_explicit_first_frame_cannot_mix_with_reference_images(self):
        provider_call = Mock()

        async def fake_resolve(url, **_kwargs):
            return f"https://files.example/{url.rsplit('/', 1)[-1]}"

        with patch.object(game_routes, "_game_video_svc", Mock(return_value=object())), \
                patch.object(game_routes.deps, "resolve_image_for_external", fake_resolve), \
                patch.object(game_routes, "_provider_call", provider_call):
            response = self.client.post(
                "/generate_video",
                json={
                    "prompt": "tiny smoke",
                    "provider": "jimeng",
                    "model": "seedance-2.0",
                    "duration": 4,
                    "resolution": "720p",
                    "image_url": "/api/files/first.png",
                    "character_refs": ["/api/files/char.png"],
                },
            )

        self.assertEqual(response.status_code, 200)
        body = _json_from_keepalive_response(response)
        self.assertIn("不能和参考图或参考视频混用", body["_error"])
        provider_call.assert_not_called()

    def test_seedance_replace_rejects_unknown_local_reference_duration(self):
        provider_call = Mock()
        with patch.object(game_routes, "_game_video_svc", Mock(return_value=object())), \
                patch.object(game_routes, "_provider_call", provider_call), \
                patch.object(game_routes.deps, "get_local_video_duration_seconds", Mock(return_value=None)):
            response = self.client.post(
                "/replace_video",
                json={
                    "provider": "jimeng",
                    "ref_video_url": "/api/files/ref.mp4",
                    "character_ref": "/api/files/char.png",
                    "prompt": "tiny smoke",
                    "resolution": "720p",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = _json_from_keepalive_response(response)
        self.assertIn("无法检测参考视频真实时长", body["_error"])
        provider_call.assert_not_called()

    def test_valid_request_reaches_provider_with_original_parameters(self):
        fake_service = FakeSeedanceService()
        with patch.object(game_routes, "_game_video_svc", return_value=fake_service), \
                patch.object(game_routes, "_provider_call", _run_provider_call):
            response = self.client.post(
                "/generate_video",
                json={
                    "prompt": "tiny smoke",
                    "provider": "jimeng",
                    "model": "seedance-1.5-pro",
                    "duration": 4,
                    "resolution": "720p",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_json_from_keepalive_response(response)["task_id"], "fake-seedance-task")
        self.assertEqual(len(fake_service.calls), 1)
        self.assertEqual(fake_service.calls[0]["model"], "seedance-1.5-pro")
        self.assertEqual(fake_service.calls[0]["duration"], 4)
        self.assertEqual(fake_service.calls[0]["resolution"], "720p")

    def test_happyhorse_reference_images_are_resolved_with_provider_size_guard(self):
        fake_service = FakeHappyHorseService()
        resolver_calls = []

        async def fake_resolve(url, **kwargs):
            resolver_calls.append({"url": url, **kwargs})
            return f"https://files.example/{url.rsplit('/', 1)[-1]}"

        async def fake_ensure_task_record(*_args, **_kwargs):
            return None

        with patch.object(game_routes, "_happyhorse", return_value=fake_service), \
                patch.object(game_routes.deps, "resolve_image_for_external", fake_resolve), \
                patch.object(game_routes, "_provider_call", _run_provider_call), \
                patch.object(game_routes, "_ensure_game_task_record", fake_ensure_task_record):
            response = self.client.post(
                "/generate_video",
                json={
                    "prompt": "tiny smoke",
                    "provider": "happyhorse",
                    "model": "happyhorse-1.0-r2v",
                    "duration": 5,
                    "resolution": "720p",
                    "character_refs": ["/api/files/huge.jpg"],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_json_from_keepalive_response(response)["task_id"], "fake-happyhorse-task")
        self.assertEqual(len(resolver_calls), 1)
        self.assertEqual(resolver_calls[0]["max_image_bytes"], game_routes.deps.HAPPYHORSE_INPUT_IMAGE_MAX_BYTES)
        self.assertTrue(resolver_calls[0]["auto_compress"])
        self.assertEqual(resolver_calls[0]["cache_prefix"], "happyhorse_ref")
        self.assertEqual(fake_service.calls[0]["reference_images"], ["https://files.example/huge.jpg"])


if __name__ == "__main__":
    unittest.main()
