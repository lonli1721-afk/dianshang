from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_USER_DATA_DIR = os.environ.get("USER_DATA_DIR")
_TEMP_USER_DATA_DIR = tempfile.mkdtemp(prefix="viral-language-policy-")
os.environ["USER_DATA_DIR"] = _TEMP_USER_DATA_DIR
sys.path.insert(0, str(ROOT / "server"))

from routers import viral_routes  # noqa: E402

_ORIGINAL_DB_PATH = viral_routes.db.get_db_path()


class ViralLanguagePolicyTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        viral_routes.db.set_db_path(_ORIGINAL_DB_PATH)
        shutil.rmtree(_TEMP_USER_DATA_DIR, ignore_errors=True)
        if _ORIGINAL_USER_DATA_DIR is None:
            os.environ.pop("USER_DATA_DIR", None)
        else:
            os.environ["USER_DATA_DIR"] = _ORIGINAL_USER_DATA_DIR

    def setUp(self):
        db_path = Path(_TEMP_USER_DATA_DIR) / f"{self._testMethodName}.db"
        viral_routes.db.set_db_path(db_path)

    def test_prompts_require_chinese_user_visible_content(self):
        req = viral_routes.ViralAnalyzeRequest(game_type="休闲游戏", target_user="年轻玩家", platform="抖音")
        analysis_prompt = viral_routes._build_analysis_prompt(req, 2)
        plan_prompt = viral_routes._build_plan_prompt(
            {"game_type": "休闲游戏", "target_user": "年轻玩家", "platform": "抖音", "optimization_goal": "提升点击"},
            [{"id": "tag-1", "label": "失败反转"}],
            viral_routes.ViralPlanRequest(tag_ids=["tag-1"], primary_tag_id="tag-1"),
        )
        rewrite_prompt = viral_routes._build_rewrite_prompt(
            {"game_type": "休闲游戏", "tags": [], "video_insights": []},
            {"title": "方案", "selected_tag_ids": []},
            ["video_prompt"],
            "更口语化",
        )

        for prompt in [analysis_prompt, plan_prompt, rewrite_prompt]:
            with self.subTest(prompt=prompt[:20]):
                self.assertIn("所有用户可见内容必须使用简体中文", prompt)
                self.assertIn("不要输出英文句子", prompt)

    def test_parse_analysis_rejects_english_user_visible_fields(self):
        text = """
        {
          "summary": "This video uses a curiosity hook and fast pacing to improve retention.",
          "video_insights": [
            {
              "video_index": 1,
              "summary": "The opening hook creates curiosity and shows gameplay rewards.",
              "hook_type": "Curiosity hook",
              "hook_strength": 8.4,
              "pacing_type": "Fast pacing",
              "visual_style": "High contrast gameplay",
              "gameplay": "Reward loop",
              "issues": ["CTA appears too late"],
              "recommendations": ["Move the reward to the first second"]
            }
          ],
          "tags": [
            {
              "id": "curiosity",
              "label": "Curiosity Hook",
              "category": "hook",
              "confidence": 0.86,
              "source_video_indices": [1],
              "source_moments": ["Video 1 0:00-0:03"],
              "evidence": "Opening question creates a curiosity gap.",
              "why_it_works": "It improves retention.",
              "application_note": "Use a stronger CTA."
            }
          ]
        }
        """

        with self.assertRaisesRegex(Exception, "包含英文内容"):
            viral_routes._parse_analysis(text, ["/api/files/a.mp4"])

    def test_common_marketing_terms_are_localized_before_display(self):
        tag = viral_routes._normalize_tag(
            {
                "label": "CTA Hook",
                "category": "hook",
                "evidence": "CTA 和 Hook 组合",
                "why_it_works": "A/B testing 适合验证",
                "application_note": "Gameplay reward 前置",
            },
            0,
        )

        self.assertEqual(tag["label"], "行动引导 钩子")
        self.assertIn("行动引导", tag["evidence"])
        self.assertIn("钩子", tag["evidence"])
        self.assertIn("对照测试", tag["why_it_works"])
        self.assertIn("玩法", tag["application_note"])

    def test_viral_observability_helpers_are_metadata_only(self):
        self.assertEqual(viral_routes._viral_model_provider("gpt-5.4"), "openai")
        self.assertEqual(viral_routes._viral_model_provider("gemini-2.5-pro"), "gemini")
        self.assertEqual(
            viral_routes._viral_error_category(Exception("503 UNAVAILABLE high demand")),
            "upstream_503",
        )
        self.assertEqual(
            viral_routes._viral_error_category(Exception("模型返回了英文内容")),
            "chinese_policy",
        )

    def test_analyze_does_not_fallback_when_model_keeps_returning_english(self):
        req = viral_routes.ViralAnalyzeRequest(
            video_ids=["video-1"],
            game_type="休闲游戏",
            target_user="年轻玩家",
            platform="抖音",
            model="gemini-2.5-flash",
        )
        request = SimpleNamespace(state=SimpleNamespace(user={"sub": "user-1"}))
        english_payload = json.dumps({
            "summary": "This video uses a curiosity hook and fast pacing.",
            "video_insights": [{
                "video_index": 1,
                "summary": "The opening hook creates curiosity.",
                "hook_type": "Curiosity hook",
                "hook_strength": 8,
                "pacing_type": "Fast pacing",
                "visual_style": "High contrast visuals",
                "gameplay": "Reward loop",
                "issues": ["CTA appears too late"],
                "recommendations": ["Move reward earlier"],
            }],
            "tags": [{
                "id": "curiosity",
                "label": "Curiosity Hook",
                "category": "hook",
                "confidence": 0.9,
                "source_video_indices": [1],
                "source_moments": ["Video 1 opening"],
                "evidence": "Opening question creates curiosity.",
                "why_it_works": "It improves retention.",
                "application_note": "Use stronger CTA.",
            }],
        })

        async def scenario():
            response = await viral_routes.analyze_videos(request, req)
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            return json.loads(b"".join(chunks).decode("utf-8").strip())

        with patch.object(viral_routes, "_resolve_video_urls", return_value=(["video-1"], ["/api/files/a.mp4"])), \
                patch.object(viral_routes, "_call_viral_model", return_value=english_payload), \
                patch.object(viral_routes, "_retry_viral_model_for_chinese", return_value=english_payload):
            result = asyncio.run(scenario())

        self.assertIn("_error", result)
        self.assertIn("模型返回了英文内容", result["_error"])
        analyses = viral_routes.db.list_viral_analyses(user_id="user-1", limit=5)
        self.assertEqual(analyses[0]["status"], "failed")
        self.assertIn("模型返回了英文内容", analyses[0]["error"])

    def test_plan_generation_does_not_fallback_when_model_is_busy(self):
        analysis = viral_routes.db.create_viral_analysis(
            user_id="user-2",
            game_type="休闲游戏",
            target_user="年轻玩家",
            platform="抖音",
            optimization_goal="提升点击",
            model="gemini-2.5-flash",
            tags=[{"id": "tag-1", "label": "失败反转", "category": "hook", "confidence": 1}],
            status="completed",
        )
        req = viral_routes.ViralPlanRequest(tag_ids=["tag-1"], primary_tag_id="tag-1")
        request = SimpleNamespace(state=SimpleNamespace(user={"sub": "user-2"}))

        async def scenario():
            response = await viral_routes.generate_plans(request, analysis["id"], req)
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            return json.loads(b"".join(chunks).decode("utf-8").strip())

        with patch.object(viral_routes, "_call_text_model", side_effect=Exception("503 UNAVAILABLE high demand")):
            result = asyncio.run(scenario())

        self.assertIn("_error", result)
        self.assertIn("模型服务当前繁忙", result["_error"])
        stored = viral_routes.db.get_viral_analysis(analysis["id"], user_id="user-2")
        self.assertEqual(stored["plans"], [])
        self.assertIn("模型服务当前繁忙", stored["error"])

    def test_no_local_fallback_helpers_remain(self):
        self.assertFalse(hasattr(viral_routes, "_local_analysis"))
        self.assertFalse(hasattr(viral_routes, "_local_plans"))


if __name__ == "__main__":
    unittest.main()
