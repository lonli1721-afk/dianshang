import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

_ORIGINAL_USER_DATA_DIR = os.environ.get("USER_DATA_DIR")
_TEMP_USER_DATA_DIR = tempfile.mkdtemp(prefix="game_ai_error_policy_")
os.environ["USER_DATA_DIR"] = _TEMP_USER_DATA_DIR

from routers import game_routes  # noqa: E402


def _json_from_keepalive_response(response):
    async def consume():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return json.loads(b"".join(chunks).decode("utf-8").strip())

    return asyncio.run(consume())


class GameAIErrorPolicyTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TEMP_USER_DATA_DIR, ignore_errors=True)
        if _ORIGINAL_USER_DATA_DIR is None:
            os.environ.pop("USER_DATA_DIR", None)
        else:
            os.environ["USER_DATA_DIR"] = _ORIGINAL_USER_DATA_DIR

    def test_friendly_ai_error_localizes_gemini_503_without_model_switch(self):
        text = game_routes._friendly_ai_error(Exception(
            "503 UNAVAILABLE. This model is currently experiencing high demand."
        ))

        self.assertEqual("模型服务当前繁忙，请稍后重试。", text)
        self.assertNotIn("UNAVAILABLE", text)
        self.assertNotIn("切换", text)

    def test_analyze_video_returns_friendly_error_for_gemini_503(self):
        class FakeAI:
            async def generate_content(self, **_kwargs):
                return SimpleNamespace(text="")

        async def provider_call(_provider, _operation, _fn):
            raise Exception("503 UNAVAILABLE. This model is currently experiencing high demand.")

        async def record_failure(*_args, **_kwargs):
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "demo.mp4").write_bytes(b"fake-video")
            req = game_routes.AnalyzeVideoRequest(video_url="/api/files/demo.mp4")

            with patch.object(game_routes, "_ai", return_value=FakeAI()), \
                    patch.object(game_routes, "_provider_call", provider_call), \
                    patch.object(game_routes, "_record_operation_failure", record_failure), \
                    patch.object(game_routes.deps, "_extract_local_file_path", return_value="/api/files/demo.mp4"), \
                    patch.object(game_routes.deps, "get_files_dir", return_value=tmp_path):
                response = asyncio.run(game_routes.analyze_video(req))
                body = _json_from_keepalive_response(response)

        self.assertEqual("模型服务当前繁忙，请稍后重试。", body["_error"])
        self.assertNotIn("UNAVAILABLE", body["_error"])
        self.assertNotIn("high demand", body["_error"])

    def test_game_prompt_english_output_is_blocked_without_translation_fallback(self):
        text = game_routes._friendly_ai_error(game_routes.GameChineseOutputError("润色提示词包含英文内容"))

        self.assertEqual("模型返回了英文提示词，系统已按规则拦截。请重新生成中文结果。", text)
        self.assertTrue(game_routes._looks_like_english_prompt_text(
            "A cinematic mobile game ad with fast camera movement and dramatic lighting."
        ))
        self.assertFalse(game_routes._looks_like_english_prompt_text(
            "竖屏 3D 游戏广告画面，角色从 UI 面板前快速冲刺，镜头轻微推进。"
        ))

    def test_refresh_prompt_requires_direct_chinese_output(self):
        async def fake_prompt_llm(prompt, **_kwargs):
            self.assertIn("必须直接使用简体中文生成最终提示词", prompt)
            self.assertIn("不要先写英文再翻译成中文", prompt)
            self.assertIn("原始提示词：", prompt)
            return "A cinematic scene with fast pacing and dramatic lighting."

        async def record_failure(*_args, **_kwargs):
            return None

        req = game_routes.RefreshPromptRequest(prompt="角色在森林里奔跑")
        with patch.object(game_routes, "_ai", return_value=object()), \
                patch.object(game_routes, "_prompt_llm_chat", fake_prompt_llm), \
                patch.object(game_routes, "_record_operation_failure", record_failure):
            response = asyncio.run(game_routes.refresh_prompt(req))
            body = _json_from_keepalive_response(response)

        self.assertEqual("模型返回了英文提示词，系统已按规则拦截。请重新生成中文结果。", body["_error"])
        self.assertNotIn("cinematic", body["_error"].lower())

    def test_analyze_prompt_sends_chinese_first_instruction(self):
        captured = {}

        async def fake_prompt_llm(prompt, **_kwargs):
            captured["prompt"] = prompt
            return "竖屏游戏广告视频，主角在森林道路中奔跑，镜头低角度跟随推进，阳光从树叶间洒下，节奏紧凑。"

        req = game_routes.AnalyzePromptRequest(description="森林跑酷广告", language="English")
        with patch.object(game_routes, "_ai", return_value=object()), \
                patch.object(game_routes, "_prompt_llm_chat", fake_prompt_llm):
            response = asyncio.run(game_routes.analyze_prompt(req))
            body = _json_from_keepalive_response(response)

        self.assertNotIn("_error", body)
        self.assertIn("必须直接使用简体中文生成最终提示词", captured["prompt"])
        self.assertIn("用户描述：森林跑酷广告", captured["prompt"])
        self.assertNotIn("Write a detailed", captured["prompt"])

    def test_analyze_video_blocks_english_reverse_prompt(self):
        class FakeAI:
            async def generate_content(self, **_kwargs):
                return SimpleNamespace(text="")

        async def provider_call(_provider, _operation, fn):
            result = await fn()
            result.text = "A vertical gameplay ad with fast pacing and a strong hook."
            return result

        async def record_failure(*_args, **_kwargs):
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "demo.mp4").write_bytes(b"fake-video")
            req = game_routes.AnalyzeVideoRequest(video_url="/api/files/demo.mp4", language="English")

            with patch.object(game_routes, "_ai", return_value=FakeAI()), \
                    patch.object(game_routes, "_provider_call", provider_call), \
                    patch.object(game_routes, "_record_operation_failure", record_failure), \
                    patch.object(game_routes.deps, "_extract_local_file_path", return_value="/api/files/demo.mp4"), \
                    patch.object(game_routes.deps, "get_files_dir", return_value=tmp_path):
                response = asyncio.run(game_routes.analyze_video(req))
                body = _json_from_keepalive_response(response)

        self.assertEqual("模型返回了英文提示词，系统已按规则拦截。请重新生成中文结果。", body["_error"])


if __name__ == "__main__":
    unittest.main()
