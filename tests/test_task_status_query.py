from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import task_status_query  # noqa: E402


class TaskStatusQueryTests(unittest.TestCase):
    def setUp(self):
        task_status_query.reset_status_query_state_for_tests()
        self.original_env = {
            "GAME_STATUS_QUERY_DEFAULT_CONCURRENCY": os.environ.get("GAME_STATUS_QUERY_DEFAULT_CONCURRENCY"),
            "GAME_STATUS_QUERY_ARK_CONCURRENCY": os.environ.get("GAME_STATUS_QUERY_ARK_CONCURRENCY"),
            "GAME_STATUS_QUERY_DASHSCOPE_CONCURRENCY": os.environ.get("GAME_STATUS_QUERY_DASHSCOPE_CONCURRENCY"),
            "GAME_STATUS_QUERY_QUEUE_TIMEOUT_SECONDS": os.environ.get("GAME_STATUS_QUERY_QUEUE_TIMEOUT_SECONDS"),
            "GAME_STATUS_QUERY_PROCESSING_TTL_SECONDS": os.environ.get("GAME_STATUS_QUERY_PROCESSING_TTL_SECONDS"),
        }

    def tearDown(self):
        task_status_query.reset_status_query_state_for_tests()
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_status_query_limits_use_provider_aliases(self):
        os.environ.pop("GAME_STATUS_QUERY_DEFAULT_CONCURRENCY", None)
        os.environ.pop("GAME_STATUS_QUERY_DASHSCOPE_CONCURRENCY", None)
        os.environ["GAME_STATUS_QUERY_ARK_CONCURRENCY"] = "2"

        async def scenario():
            jimeng = task_status_query.get_status_query_limiter("jimeng")
            seedance = task_status_query.get_status_query_limiter("seedance")
            dashscope = task_status_query.get_status_query_limiter("happyhorse")
            return jimeng, seedance, dashscope

        jimeng, seedance, dashscope = asyncio.run(scenario())

        self.assertIs(jimeng, seedance)
        self.assertEqual(jimeng.provider_key, "ark")
        self.assertEqual(jimeng.limit, 2)
        self.assertEqual(dashscope.provider_key, "dashscope")
        self.assertEqual(dashscope.limit, 1)

    def test_concurrent_same_task_is_coalesced(self):
        calls = 0

        async def scenario():
            nonlocal calls
            release = asyncio.Event()

            async def query():
                nonlocal calls
                calls += 1
                await release.wait()
                return {"task_id": "task-1", "status": "processing"}

            tasks = [
                asyncio.create_task(task_status_query.run_status_query("jimeng", "task-1", query))
                for _ in range(5)
            ]
            await asyncio.sleep(0.05)
            release.set()
            results = await asyncio.gather(*tasks)
            snapshot = task_status_query.status_query_snapshot()["providers"]["ark"]
            return results, snapshot

        results, snapshot = asyncio.run(scenario())

        self.assertEqual(calls, 1)
        self.assertEqual([row["status"] for row in results], ["processing"] * 5)
        self.assertEqual(snapshot["total_coalesced"], 4)
        self.assertEqual(snapshot["total_started"], 1)

    def test_processing_status_uses_short_ttl_cache(self):
        os.environ["GAME_STATUS_QUERY_PROCESSING_TTL_SECONDS"] = "3"
        calls = 0

        async def scenario():
            nonlocal calls

            async def query():
                nonlocal calls
                calls += 1
                return {"task_id": "task-2", "status": "processing"}

            first = await task_status_query.run_status_query("vidu", "task-2", query)
            second = await task_status_query.run_status_query("vidu", "task-2", query)
            snapshot = task_status_query.status_query_snapshot()["providers"]["vidu"]
            return first, second, snapshot

        first, second, snapshot = asyncio.run(scenario())

        self.assertEqual(calls, 1)
        self.assertEqual(first["status"], "processing")
        self.assertEqual(second["status"], "processing")
        self.assertEqual(snapshot["total_cache_hits"], 1)
        self.assertEqual(snapshot["cache_entries"], 1)

    def test_completed_status_is_not_cached(self):
        calls = 0

        async def scenario():
            nonlocal calls

            async def query():
                nonlocal calls
                calls += 1
                return {"task_id": "task-3", "status": "completed", "video_url": "/api/files/a.mp4"}

            await task_status_query.run_status_query("vidu", "task-3", query)
            await task_status_query.run_status_query("vidu", "task-3", query)
            snapshot = task_status_query.status_query_snapshot()["providers"]["vidu"]
            return snapshot

        snapshot = asyncio.run(scenario())

        self.assertEqual(calls, 2)
        self.assertEqual(snapshot["total_cache_hits"], 0)
        self.assertEqual(snapshot["cache_entries"], 0)

    def test_queue_timeout_returns_busy_error_and_snapshot_counts_it(self):
        os.environ["GAME_STATUS_QUERY_DEFAULT_CONCURRENCY"] = "1"
        os.environ["GAME_STATUS_QUERY_QUEUE_TIMEOUT_SECONDS"] = "0.01"

        async def scenario():
            started = asyncio.Event()
            release = asyncio.Event()

            async def first():
                started.set()
                await release.wait()
                return {"task_id": "task-4", "status": "processing"}

            async def second():
                return {"task_id": "task-5", "status": "processing"}

            task_one = asyncio.create_task(task_status_query.run_status_query("custom", "task-4", first))
            await started.wait()
            with self.assertRaises(task_status_query.StatusQueryBusyError):
                await task_status_query.run_status_query("custom", "task-5", second)
            release.set()
            await task_one
            return task_status_query.status_query_snapshot()["providers"]["custom"]

        snapshot = asyncio.run(scenario())

        self.assertEqual(snapshot["active"], 0)
        self.assertEqual(snapshot["waiting"], 0)
        self.assertEqual(snapshot["total_timeouts"], 1)


if __name__ == "__main__":
    unittest.main()
