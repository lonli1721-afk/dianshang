import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIRAL_PAGE = ROOT / "react-ui" / "src" / "pages" / "viral" / "ViralWorkbenchPage.jsx"
ANALYSIS_BRIEF_STRIP = ROOT / "react-ui" / "src" / "pages" / "viral" / "components" / "AnalysisBriefStrip.jsx"
VIRAL_WORKBENCH_HEADER = ROOT / "react-ui" / "src" / "pages" / "viral" / "components" / "ViralWorkbenchHeader.jsx"


class FrontendViralBoundaryTests(unittest.TestCase):
    def test_script_target_duration_supports_short_ads(self):
        page = VIRAL_PAGE.read_text(encoding="utf-8")

        self.assertIn("const durationOptions = ['5s', '10s', '15s', '20s', '30s']", page)
        self.assertIn("target_duration: '20s'", page)
        self.assertIn("const sceneDurationOptions = [3, 5, 10, 15]", page)

    def test_viral_scene_apply_preferences_are_persisted_safely(self):
        page = VIRAL_PAGE.read_text(encoding="utf-8")

        self.assertIn("VIRAL_SCENE_APPLY_PREFS_KEY", page)
        self.assertIn("function sanitizeSceneApplyPreferences", page)
        self.assertIn("loadSceneApplyPreferences()", page)
        self.assertIn("saveSceneApplyPreferences({", page)
        self.assertIn("aspect_ratio: sceneApplyConfig.aspect_ratio", page)
        self.assertIn("savedSceneApplyPreferences.aspect_ratio || '9:16'", page)
        self.assertNotIn("project_id: savedSceneApplyPreferences", page)
        self.assertNotIn("scene_id: savedSceneApplyPreferences", page)

    def test_batch_script_selection_avoids_nested_input_inside_card_button(self):
        page = VIRAL_PAGE.read_text(encoding="utf-8")

        self.assertIn('role="checkbox"', page)
        self.assertIn("aria-checked={checked}", page)
        self.assertIn("toggleBatchPlan(plan.id)", page)
        self.assertIn('<div\n                        key={plan.id}\n                        role="button"', page)
        self.assertNotIn('className="viral-script-card-check" title={batchDisabled', page)
        self.assertNotIn('type="checkbox"\n                                checked={checked}', page)

    def test_analysis_brief_strip_is_controlled_presentation(self):
        source = ANALYSIS_BRIEF_STRIP.read_text(encoding="utf-8")

        self.assertIn("export default function AnalysisBriefStrip", source)
        self.assertIn("onToggleExpanded", source)
        self.assertIn("onFormChange('game_type'", source)
        self.assertIn("onFormChange('optimization_goal'", source)
        self.assertIn("platformOptions.map", source)
        self.assertIn("models.map", source)

        forbidden = [
            "api.",
            "fetch(",
            "localStorage",
            "sessionStorage",
            "document.",
            "window.",
            "navigator.",
            "setInterval",
            "setTimeout",
            "useEffect",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_viral_page_keeps_brief_state_and_side_effects(self):
        page = VIRAL_PAGE.read_text(encoding="utf-8")

        self.assertIn("import AnalysisBriefStrip from './components/AnalysisBriefStrip'", page)
        self.assertIn("<AnalysisBriefStrip", page)
        self.assertIn("expanded={shouldShowBriefForm}", page)
        self.assertIn("onToggleExpanded={() => setBriefExpanded(prev => !prev)}", page)
        self.assertIn("onFormChange={updateForm}", page)
        self.assertIn("api.post('/api/viral/analyze'", page)
        self.assertIn("useGameTaskPolling", page)
        self.assertNotIn("className={`viral-condition-strip is-embedded", page)

    def test_viral_workbench_header_is_controlled_presentation(self):
        source = VIRAL_WORKBENCH_HEADER.read_text(encoding="utf-8")

        self.assertIn("export default function ViralWorkbenchHeader", source)
        self.assertIn("onStartNewAnalysis", source)
        self.assertIn("onRefresh", source)
        self.assertIn("onActivateAnalysis(item)", source)
        self.assertIn("workflowSteps.map", source)
        self.assertIn("stats.map", source)

        forbidden = [
            "api.",
            "fetch(",
            "localStorage",
            "sessionStorage",
            "document.",
            "window.",
            "navigator.",
            "setInterval",
            "setTimeout",
            "useEffect",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_viral_page_uses_header_shell_without_moving_side_effects(self):
        page = VIRAL_PAGE.read_text(encoding="utf-8")

        self.assertIn("import ViralWorkbenchHeader from './components/ViralWorkbenchHeader'", page)
        self.assertIn("<ViralWorkbenchHeader", page)
        self.assertIn("onRefresh={refreshData}", page)
        self.assertIn("onActivateAnalysis={activateAnalysis}", page)
        self.assertIn("workflowSteps={workflowSteps}", page)
        self.assertIn("api.get('/api/viral/videos')", page)
        self.assertIn("api.get('/api/viral/analyses')", page)
        self.assertIn("api.post('/api/viral/analyze'", page)
        self.assertIn("useGameTaskPolling", page)
        self.assertNotIn('className="viral-topbar viral-creative-topbar"', page)
        self.assertNotIn('className="viral-workflow-strip"', page)


if __name__ == "__main__":
    unittest.main()
