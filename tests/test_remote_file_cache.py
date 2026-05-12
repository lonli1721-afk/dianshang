from __future__ import annotations

import atexit
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
MODULE_DATA_DIR = tempfile.TemporaryDirectory(prefix="game-video-remote-cache-test-")
atexit.register(MODULE_DATA_DIR.cleanup)
os.environ["USER_DATA_DIR"] = MODULE_DATA_DIR.name
sys.path.insert(0, str(ROOT / "server"))

import deps  # noqa: E402


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        chunks: list[bytes] | None = None,
        headers: dict[str, str] | None = None,
        url: str = "https://provider.example.com/result.mp4?token=secret",
    ):
        self.status_code = status_code
        self._chunks = chunks if chunks is not None else [b"video"]
        self.headers = headers or {"content-type": "video/mp4", "content-length": "5"}
        self.request = SimpleNamespace(url=url)

    async def aiter_bytes(self, _chunk_size: int):
        for chunk in self._chunks:
            yield chunk


class RemoteFileCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_files_dir = deps.get_files_dir()
        deps.set_files_dir(Path(self.tempdir.name))

    def tearDown(self):
        deps.set_files_dir(self.original_files_dir)
        self.tempdir.cleanup()

    async def test_extract_local_file_path_supports_signed_public_file_urls(self):
        self.assertEqual(
            deps._extract_local_file_path("https://example.com/public-files/ref%20video.mp4?expires=1&sig=abc"),
            "/api/files/ref video.mp4",
        )
        self.assertEqual(
            deps._extract_local_file_path("/public-files/ref.mp4?expires=1&sig=abc"),
            "/api/files/ref.mp4",
        )
        self.assertEqual(deps._extract_local_file_path("https://example.com/public-files/../ref.mp4"), "")

    async def test_http_failure_raises_structured_safe_error(self):
        response = FakeResponse(
            status_code=403,
            chunks=[],
            headers={"content-type": "text/html", "content-length": "12"},
            url="https://signed.example.com/video.mp4?token=very-secret",
        )

        with self.assertRaises(deps.RemoteFileCacheError) as ctx:
            await deps._write_response_stream_to_local(response, ".mp4")

        error = ctx.exception
        self.assertEqual(error.reason, "remote_http_403")
        self.assertIn("HTTP 403", error.user_message())
        self.assertIn("content-type=text/html", error.user_message())
        self.assertEqual(error.safe_context()["remote_host"], "signed.example.com")
        self.assertNotIn("very-secret", str(error.safe_context()))

    async def test_empty_video_download_is_rejected(self):
        response = FakeResponse(
            status_code=200,
            chunks=[b"", b""],
            headers={"content-type": "video/mp4", "content-length": "0"},
        )

        with self.assertRaises(deps.RemoteFileCacheError) as ctx:
            await deps._write_response_stream_to_local(response, ".mp4")

        self.assertEqual(ctx.exception.reason, "remote_empty_response")
        self.assertIn("远程文件下载为空", ctx.exception.user_message())
        self.assertFalse(list(Path(self.tempdir.name).glob("cached_*.mp4")))

    async def test_local_write_failure_is_classified(self):
        original_get_files_dir = deps.get_files_dir
        deps.get_files_dir = lambda: Path(self.tempdir.name) / "missing-parent" / "files"  # type: ignore[assignment]
        try:
            response = FakeResponse(status_code=200, chunks=[b"video"])

            with self.assertRaises(deps.RemoteFileCacheError) as ctx:
                await deps._write_response_stream_to_local(response, ".mp4")
        finally:
            deps.get_files_dir = original_get_files_dir  # type: ignore[assignment]

        self.assertEqual(ctx.exception.reason, "local_write_failed")
        self.assertIn("本地写入失败", ctx.exception.user_message())
        self.assertIn("FileNotFoundError", ctx.exception.user_message())

    async def test_cache_remote_file_strict_sanitizes_signed_url_and_non_strict_keeps_compatibility(self):
        signed_url = "https://signed.example.com/video.mp4?token=very-secret"
        original_stream = deps.stream_remote_file_to_local

        async def fail_download(url: str, ext: str = "") -> str:
            raise deps.RemoteFileCacheError(
                "remote_http_404",
                url=url,
                status_code=404,
                content_type="text/html",
                content_length="0",
            )

        deps.stream_remote_file_to_local = fail_download  # type: ignore[assignment]
        try:
            with self.assertRaises(HTTPException) as ctx:
                await deps.cache_remote_file(
                    signed_url,
                    ".mp4",
                    strict=True,
                    strict_error_message="视频任务已完成，但结果视频保存到本地失败",
                )
            self.assertIn("HTTP 404", str(ctx.exception.detail))
            self.assertNotIn("very-secret", str(ctx.exception.detail))

            fallback = await deps.cache_remote_file(signed_url, ".mp4", strict=False)
            self.assertEqual(fallback, signed_url)
        finally:
            deps.stream_remote_file_to_local = original_stream  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
