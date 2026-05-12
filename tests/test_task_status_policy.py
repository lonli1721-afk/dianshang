from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from task_status_policy import (  # noqa: E402
    COMPLETED_VIDEO_MISSING_ERROR,
    is_failed_task_status,
    is_success_task_status,
    provider_video_cache_error,
    should_retry_failed_provider_video_cache,
    terminal_task_result_from_db,
)


class TaskStatusPolicyTests(unittest.TestCase):
    def test_success_and_failure_status_sets(self):
        self.assertTrue(is_success_task_status("completed"))
        self.assertTrue(is_success_task_status("succeeded"))
        self.assertTrue(is_success_task_status("success"))
        self.assertFalse(is_success_task_status("processing"))

        self.assertTrue(is_failed_task_status("failed"))
        self.assertTrue(is_failed_task_status("cancelled"))
        self.assertFalse(is_failed_task_status("completed"))

    def test_provider_video_errors_are_user_actionable(self):
        self.assertIn("上游未返回视频地址", COMPLETED_VIDEO_MISSING_ERROR)
        error = provider_video_cache_error(RuntimeError("HTTP 403"))

        self.assertIn("结果视频保存到本地失败", error)
        self.assertIn("重新拉取结果", error)

    def test_provider_video_cache_error_does_not_duplicate_wrapped_detail(self):
        wrapped = HTTPException(502, "视频任务已完成，但结果视频保存到本地失败：TimeoutError")

        error = provider_video_cache_error(wrapped)

        self.assertEqual(error.count("结果视频保存到本地失败"), 1)
        self.assertIn("TimeoutError", error)
        self.assertTrue(error.endswith("可先点击“重新拉取结果”。"))

    def test_provider_video_cache_error_fills_empty_detail(self):
        wrapped = HTTPException(502, "视频任务已完成，但结果视频保存到本地失败：")

        error = provider_video_cache_error(wrapped)

        self.assertEqual(error.count("结果视频保存到本地失败"), 1)
        self.assertIn("未知错误", error)
        self.assertTrue(error.endswith("可先点击“重新拉取结果”。"))

    def test_terminal_task_result_uses_db_without_provider_for_completed_local_video(self):
        result = terminal_task_result_from_db(
            "external-1",
            {
                "status": "completed",
                "video_url": "/api/files/done.mp4",
                "error": "",
                "provider": "jimeng",
                "model": "seedance-2.0",
            },
        )

        self.assertEqual(result["task_id"], "external-1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["video_url"], "/api/files/done.mp4")

    def test_terminal_task_result_uses_db_without_provider_for_failed_or_expired(self):
        failed = terminal_task_result_from_db(
            "external-2",
            {"status": "failed", "video_url": "", "error": "上游失败", "provider": "vidu", "model": "vidu"},
        )
        expired = terminal_task_result_from_db(
            "external-3",
            {"status": "expired", "video_url": "", "error": "链接过期", "provider": "jimeng", "model": "seedance"},
        )
        processing = terminal_task_result_from_db(
            "external-4",
            {"status": "processing", "video_url": "", "error": "", "provider": "jimeng", "model": "seedance"},
        )
        completed_remote = terminal_task_result_from_db(
            "external-5",
            {"status": "completed", "video_url": "https://example.com/a.mp4", "error": "", "provider": "jimeng"},
        )

        self.assertEqual(failed["error"], "上游失败")
        self.assertEqual(expired["status"], "expired")
        self.assertIsNone(processing)
        self.assertIsNone(completed_remote)

    def test_only_provider_cache_failures_are_retryable(self):
        retryable = {
            "status": "failed",
            "video_url": "",
            "error": provider_video_cache_error(RuntimeError("HTTP 403")),
            "provider": "jimeng",
            "external_task_id": "external-1",
        }
        normal_failed = {
            **retryable,
            "error": "上游生成失败：InvalidParameter",
        }
        already_has_video = {
            **retryable,
            "video_url": "/api/files/done.mp4",
        }

        self.assertTrue(should_retry_failed_provider_video_cache(retryable))
        self.assertFalse(should_retry_failed_provider_video_cache(normal_failed))
        self.assertFalse(should_retry_failed_provider_video_cache(already_has_video))


if __name__ == "__main__":
    unittest.main()
