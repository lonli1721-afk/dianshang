import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PAGE = ROOT / "react-ui" / "src" / "pages" / "SettingsPage.jsx"
SETTINGS_LAYOUT = ROOT / "react-ui" / "src" / "pages" / "settings" / "components" / "SettingsLayout.jsx"


class FrontendSettingsBoundaryTests(unittest.TestCase):
    def test_settings_layout_is_presentation_only(self):
        source = SETTINGS_LAYOUT.read_text(encoding="utf-8")

        self.assertIn("export default function SettingsLayout", source)
        self.assertIn("onNavChange(item.id)", source)
        self.assertIn("{children}", source)

        forbidden = [
            "api.",
            "fetch(",
            "localStorage",
            "sessionStorage",
            "document.",
            "window.",
            "setInterval",
            "setTimeout",
            "useEffect",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_settings_page_keeps_settings_side_effects(self):
        page = SETTINGS_PAGE.read_text(encoding="utf-8")

        self.assertIn("import SettingsLayout from './settings/components/SettingsLayout'", page)
        self.assertIn("<SettingsLayout", page)
        self.assertIn("onNavChange={setActiveNav}", page)
        self.assertIn("api.get('/api/settings')", page)
        self.assertIn("api.post('/api/settings'", page)
        self.assertIn("fetch(`${base}/api/local-config`)", page)


if __name__ == "__main__":
    unittest.main()
