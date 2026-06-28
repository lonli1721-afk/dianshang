import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from toapis_service import ToapisVideoService  # noqa: E402


class _FakeResponse:
    status_code = 200
    text = '{"id":"task-123"}'

    def json(self):
        return {"id": "task-123"}


class ToapisVideoServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_seedance_15_reference_image_uses_i2v_task_type(self):
        captured = {}

        async def fake_request(_label, _method, _url, **kwargs):
            captured.update(kwargs.get("json") or {})
            return _FakeResponse()

        service = ToapisVideoService("test-key")
        with patch("toapis_service._toapis_request_with_retry", fake_request):
            result = await service.generate_video(
                prompt="product ad",
                model="doubao-seedance-1-5-pro",
                aspect_ratio="9:16",
                duration=5,
                resolution="720p",
                image_urls=["https://example.com/storyboard.png", "https://example.com/extra.png"],
            )

        self.assertEqual(result["task_id"], "task-123")
        self.assertEqual(captured["model"], "doubao-seedance-1-5-pro")
        self.assertEqual(captured["task_type"], "i2v")
        self.assertEqual(
            captured["image_with_roles"],
            [{"url": "https://example.com/storyboard.png", "role": "first_frame"}],
        )
        self.assertNotIn("image_url", captured)
        self.assertNotIn("image_urls", captured)


if __name__ == "__main__":
    unittest.main()
