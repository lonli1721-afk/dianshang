from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from game_video_service import GameJimengService  # noqa: E402


class _FakeResponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {"task_id": "fake-task"}


class _FakeAsyncClient:
    payloads: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self.payloads.append(json or {})
        return _FakeResponse()


class GameVideoServicePayloadLimitTests(unittest.TestCase):
    def setUp(self):
        _FakeAsyncClient.payloads.clear()

    def test_seedance_standard_generation_sends_registry_ref_image_limit(self):
        refs = [f"data:image/png;base64,ref{idx}" for idx in range(9)]
        with patch("game_video_service.httpx.AsyncClient", _FakeAsyncClient):
            result = asyncio.run(
                GameJimengService("test-key").generate_video(
                    prompt="tiny smoke",
                    model="seedance-2.0",
                    duration=5,
                    resolution="720p",
                    reference_images=refs,
                )
            )

        self.assertEqual(result["task_id"], "fake-task")
        content = _FakeAsyncClient.payloads[0]["content"]
        ref_image_count = sum(1 for item in content if item.get("role") == "reference_image")
        self.assertEqual(ref_image_count, 9)


if __name__ == "__main__":
    unittest.main()
