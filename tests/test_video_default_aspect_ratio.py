import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VideoDefaultAspectRatioTests(unittest.TestCase):
    def test_frontend_new_video_scenes_default_to_vertical_without_removing_manual_choices(self):
        helper = (ROOT / "react-ui" / "src" / "pages" / "game" / "gameVideoPageHelpers.js").read_text(encoding="utf-8")
        scene_card = (ROOT / "react-ui" / "src" / "pages" / "game" / "components" / "SceneVideoCard.jsx").read_text(encoding="utf-8")

        self.assertIn("duration: 5, aspectRatio: '9:16', videoResolution: '720p'", helper)
        self.assertIn('<option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option>', scene_card)

    def test_backend_video_generation_defaults_to_vertical_when_client_omits_ratio(self):
        game_routes = (ROOT / "server" / "routers" / "game_routes.py").read_text(encoding="utf-8")
        game_video_service = (ROOT / "server" / "game_video_service.py").read_text(encoding="utf-8")
        jimeng_service = (ROOT / "server" / "jimeng_service.py").read_text(encoding="utf-8")
        vidu_service = (ROOT / "server" / "vidu_service.py").read_text(encoding="utf-8")
        happyhorse_service = (ROOT / "server" / "happyhorse_service.py").read_text(encoding="utf-8")

        self.assertIn('aspect_ratio: str = "9:16"', game_routes)
        self.assertNotIn('aspect_ratio: str = "16:9"', game_routes)

        for source in (game_video_service, jimeng_service):
            with self.subTest(source="seedance"):
                self.assertIn('ratio: str = "9:16"', source)
                self.assertNotIn('ratio: str = "16:9"', source)

        self.assertIn('aspect_ratio: str = "9:16"', vidu_service)
        self.assertNotIn('aspect_ratio: str = "16:9"', vidu_service)

        self.assertIn('return "9:16"', happyhorse_service)
        self.assertIn('aspect_ratio: str = "9:16"', happyhorse_service)
        self.assertNotIn('return "16:9"', happyhorse_service)
        self.assertNotIn('aspect_ratio: str = "16:9"', happyhorse_service)


if __name__ == "__main__":
    unittest.main()
