from __future__ import annotations

import asyncio
import sys
import unittest
from types import ModuleType
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

try:
    from google import genai as _genai  # noqa: F401
except (ImportError, ModuleNotFoundError):
    google_module = ModuleType("google")
    genai_module = ModuleType("google.genai")
    types_module = ModuleType("google.genai.types")
    genai_module.Client = lambda *args, **kwargs: None
    genai_module.types = types_module
    google_module.genai = genai_module
    sys.modules["google"] = google_module
    sys.modules["google.genai"] = genai_module
    sys.modules["google.genai.types"] = types_module

import ai_service  # noqa: E402


class AIServiceKeyPoolTests(unittest.TestCase):
    def setUp(self):
        self.original_client = ai_service.genai.Client

    def tearDown(self):
        ai_service.genai.Client = self.original_client

    def test_split_api_keys_dedupes_and_preserves_order(self):
        self.assertEqual(
            ai_service.split_api_keys(" key-a, key-b\nkey-a; key-c "),
            ["key-a", "key-b", "key-c"],
        )
        self.assertEqual(ai_service.split_api_keys(["a", "b", "a", ""]), ["a", "b"])

    def test_key_pool_snapshot_is_redacted(self):
        ai_service.genai.Client = lambda api_key, **_kwargs: SimpleNamespace(api_key=api_key)

        async def scenario():
            svc = ai_service.AIService(
                api_key="gemini-secret-0001",
                api_keys=["gemini-secret-0001", "gemini-secret-0002"],
                cooldown_seconds=30,
                max_concurrency_per_key=1,
                project_max_concurrency=1,
                project_min_interval_seconds=0,
                queue_timeout_seconds=1,
            )
            return svc.key_pool_snapshot(scope="unit")

        snapshot = asyncio.run(scenario())

        self.assertEqual(snapshot["scope"], "unit")
        self.assertEqual(snapshot["key_count"], 2)
        self.assertEqual(snapshot["project"]["limit"], 1)
        self.assertEqual(snapshot["keys"][0]["key_hint"], "...0001")
        self.assertNotIn("gemini-secret", str(snapshot))

    def test_rate_limited_key_cools_down_and_next_key_is_used(self):
        calls: list[str] = []

        class FakeModels:
            def __init__(self, key: str):
                self.key = key

            def generate_content(self, **_kwargs):
                calls.append(self.key)
                if self.key == "gemini-secret-0001":
                    raise Exception("HTTP 429 RESOURCE_EXHAUSTED")
                return SimpleNamespace(text=f"ok:{self.key}")

        def fake_client(api_key, **_kwargs):
            return SimpleNamespace(api_key=api_key, models=FakeModels(api_key))

        ai_service.genai.Client = fake_client

        async def scenario():
            svc = ai_service.AIService(
                api_key="gemini-secret-0001",
                api_keys=["gemini-secret-0001", "gemini-secret-0002"],
                cooldown_seconds=30,
                max_concurrency_per_key=1,
                project_max_concurrency=1,
                project_min_interval_seconds=0,
                queue_timeout_seconds=1,
            )
            response = await svc.generate_content(model="test-model", contents="hello")
            return response, svc.key_pool_snapshot()

        response, snapshot = asyncio.run(scenario())

        self.assertEqual(response.text, "ok:gemini-secret-0002")
        self.assertEqual(calls, ["gemini-secret-0001", "gemini-secret-0002"])
        self.assertEqual(snapshot["cooling_down_count"], 1)
        self.assertEqual(snapshot["keys"][0]["total_rate_limited"], 1)
        self.assertEqual(snapshot["keys"][1]["total_started"], 1)


if __name__ == "__main__":
    unittest.main()
