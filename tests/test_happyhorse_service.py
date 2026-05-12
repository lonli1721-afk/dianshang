from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from happyhorse_service import HappyHorseService, _localize_happyhorse_error  # noqa: E402


class _FakeResponse:
    status_code = 200

    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    payload: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return _FakeResponse(self.payload)


class HappyHorseServiceTests(unittest.TestCase):
    def _query(self, payload: dict) -> dict:
        _FakeAsyncClient.payload = payload
        with patch("happyhorse_service.httpx.AsyncClient", _FakeAsyncClient):
            return asyncio.run(HappyHorseService("key").query_task("task-1"))

    def test_localize_billing_error_before_generic_access_denied(self):
        text = _localize_happyhorse_error(
            "Access denied, please make sure your account is in good standing.",
            "Arrearage",
        )

        self.assertIn("欠费", text)

    def test_query_task_extracts_video_url_from_results_dict(self):
        result = self._query({
            "output": {
                "task_status": "SUCCEEDED",
                "results": {"video_url": "https://example.com/from-results-dict.mp4"},
            }
        })

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["video_url"], "https://example.com/from-results-dict.mp4")

    def test_query_task_extracts_video_url_from_results_list(self):
        result = self._query({
            "output": {
                "task_status": "SUCCEEDED",
                "results": [{"url": "https://example.com/from-results-list.mp4"}],
            }
        })

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["video_url"], "https://example.com/from-results-list.mp4")

    def test_query_task_keeps_root_video_url_compatibility(self):
        result = self._query({
            "output": {"task_status": "SUCCEEDED"},
            "video_url": "https://example.com/from-root.mp4",
        })

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["video_url"], "https://example.com/from-root.mp4")


if __name__ == "__main__":
    unittest.main()
