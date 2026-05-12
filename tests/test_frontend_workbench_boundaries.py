import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC_DIR = ROOT / "react-ui" / "src"
GAME_DIR = ROOT / "react-ui" / "src" / "pages" / "game"


class FrontendWorkbenchBoundaryTests(unittest.TestCase):
    def test_game_workbench_video_elements_disable_preload(self):
        video_tags_missing_preload_none = []

        for path in sorted(REACT_SRC_DIR.rglob("*.jsx")):
            source = path.read_text(encoding="utf-8")
            for match in re.finditer(r"<video\b[^>]*>", source, flags=re.DOTALL):
                tag = match.group(0)
                if 'preload="none"' not in tag:
                    relative_path = path.relative_to(ROOT)
                    line_number = source[:match.start()].count("\n") + 1
                    video_tags_missing_preload_none.append(f"{relative_path}:{line_number}")

        self.assertEqual([], video_tags_missing_preload_none)

    def test_game_workbench_image_elements_are_lazy_decoded(self):
        image_tags_missing_lazy_decode = []

        for path in sorted((GAME_DIR / "components").glob("*.jsx")):
            source = path.read_text(encoding="utf-8")
            for match in re.finditer(r"<img\b[^>]*>", source, flags=re.DOTALL):
                tag = match.group(0)
                if 'loading="lazy"' not in tag or 'decoding="async"' not in tag:
                    line_number = source[:match.start()].count("\n") + 1
                    image_tags_missing_lazy_decode.append(f"{path.name}:{line_number}")

        self.assertEqual([], image_tags_missing_lazy_decode)

    def test_inactive_replace_panel_does_not_mount_media_nodes(self):
        replace_panel = (GAME_DIR / "components" / "ReplaceVideoPanel.jsx").read_text(encoding="utf-8")

        self.assertIn("if (!active) return null", replace_panel)
        self.assertNotIn("display: active ? 'block' : 'none'", replace_panel)

    def test_generation_record_panel_caps_duplicate_history_previews(self):
        record_panel = (GAME_DIR / "components" / "GenerationRecordPanel.jsx").read_text(encoding="utf-8")

        self.assertIn("RECORD_HISTORY_PREVIEW_LIMIT = 3", record_panel)
        self.assertIn(".slice(0, RECORD_HISTORY_PREVIEW_LIMIT)", record_panel)

    def test_game_page_uses_central_upload_hook(self):
        game_page = (GAME_DIR / "GameVideoPage.jsx").read_text(encoding="utf-8")
        file_upload_hook = (GAME_DIR / "useFileUploadActions.js").read_text(encoding="utf-8")
        reverse_hook = (GAME_DIR / "useReverseVideoActions.js").read_text(encoding="utf-8")
        scene_media_hook = (GAME_DIR / "useSceneMediaActions.js").read_text(encoding="utf-8")
        scene_image_hook = (GAME_DIR / "useSceneImageGenerationActions.js").read_text(encoding="utf-8")
        standalone_image_hook = (GAME_DIR / "useStandaloneImageGenerationActions.js").read_text(encoding="utf-8")
        scene_prompt_hook = (GAME_DIR / "useScenePromptActions.js").read_text(encoding="utf-8")
        scene_video_hook = (GAME_DIR / "useSceneVideoGenerationActions.js").read_text(encoding="utf-8")
        scene_video_history_hook = (GAME_DIR / "useSceneVideoHistoryActions.js").read_text(encoding="utf-8")
        replace_video_hook = (GAME_DIR / "useReplaceVideoActions.js").read_text(encoding="utf-8")
        replace_panel_hook = (GAME_DIR / "useReplaceVideoPanelActions.js").read_text(encoding="utf-8")

        self.assertIn("/api/game/upload", file_upload_hook)
        self.assertNotIn("api.upload", game_page)
        self.assertNotIn("/api/game/upload", reverse_hook)
        self.assertNotIn("/api/game/upload", scene_media_hook)
        self.assertNotIn("/api/game/upload", scene_image_hook)
        self.assertNotIn("/api/game/upload", standalone_image_hook)
        self.assertNotIn("/api/game/upload", scene_prompt_hook)
        self.assertNotIn("/api/game/upload", scene_video_hook)
        self.assertNotIn("/api/game/upload", scene_video_history_hook)
        self.assertNotIn("/api/game/upload", replace_video_hook)
        self.assertNotIn("/api/game/upload", replace_panel_hook)

    def test_scene_image_generation_hook_does_not_touch_video_endpoints(self):
        scene_image_hook = (GAME_DIR / "useSceneImageGenerationActions.js").read_text(encoding="utf-8")

        self.assertNotIn("/api/game/generate_video", scene_image_hook)
        self.assertNotIn("/api/game/replace_video", scene_image_hook)
        self.assertNotIn("/api/game/analyze_video", scene_image_hook)

    def test_standalone_image_generation_hook_does_not_touch_video_endpoints(self):
        standalone_image_hook = (GAME_DIR / "useStandaloneImageGenerationActions.js").read_text(encoding="utf-8")

        self.assertNotIn("/api/game/generate_video", standalone_image_hook)
        self.assertNotIn("/api/game/replace_video", standalone_image_hook)
        self.assertNotIn("/api/game/analyze_video", standalone_image_hook)

    def test_scene_prompt_hook_only_touches_prompt_endpoints(self):
        scene_prompt_hook = (GAME_DIR / "useScenePromptActions.js").read_text(encoding="utf-8")

        self.assertIn("/api/game/analyze_prompt", scene_prompt_hook)
        self.assertIn("/api/game/refresh_prompt", scene_prompt_hook)
        self.assertNotIn("/api/game/generate_video", scene_prompt_hook)
        self.assertNotIn("/api/game/generate_image", scene_prompt_hook)
        self.assertNotIn("/api/game/replace_video", scene_prompt_hook)
        self.assertNotIn("/api/game/analyze_video", scene_prompt_hook)

    def test_scene_video_generation_hook_only_touches_generate_video_endpoint(self):
        scene_video_hook = (GAME_DIR / "useSceneVideoGenerationActions.js").read_text(encoding="utf-8")
        game_page = (GAME_DIR / "GameVideoPage.jsx").read_text(encoding="utf-8")

        self.assertIn("/api/game/generate_video", scene_video_hook)
        self.assertNotIn("/api/game/generate_video", game_page)
        self.assertNotIn("/api/game/generate_image", scene_video_hook)
        self.assertNotIn("/api/game/replace_video", scene_video_hook)
        self.assertNotIn("/api/game/analyze_video", scene_video_hook)
        self.assertNotIn("/api/game/analyze_prompt", scene_video_hook)
        self.assertNotIn("/api/game/refresh_prompt", scene_video_hook)
        self.assertNotIn("localStorage", scene_video_hook)
        self.assertNotIn("writeWorkbenchCache", scene_video_hook)
        self.assertNotIn("document.createElement", scene_video_hook)
        self.assertNotIn("navigator.clipboard", scene_video_hook)
        self.assertNotIn("setInterval", scene_video_hook)

    def test_scene_video_history_hook_does_not_touch_api_or_browser_globals(self):
        scene_video_history_hook = (GAME_DIR / "useSceneVideoHistoryActions.js").read_text(encoding="utf-8")

        self.assertNotIn("/api/game/", scene_video_history_hook)
        self.assertNotIn("api.", scene_video_history_hook)
        self.assertNotIn("localStorage", scene_video_history_hook)
        self.assertNotIn("writeWorkbenchCache", scene_video_history_hook)
        self.assertNotIn("document.createElement", scene_video_history_hook)
        self.assertNotIn("navigator.clipboard", scene_video_history_hook)
        self.assertNotIn("setInterval", scene_video_history_hook)
        self.assertNotIn("setTimeout", scene_video_history_hook)

    def test_model_busy_errors_are_not_retried_or_suggested_as_model_switch(self):
        game_page = (GAME_DIR / "GameVideoPage.jsx").read_text(encoding="utf-8")
        helpers = (GAME_DIR / "gameVideoPageHelpers.js").read_text(encoding="utf-8")
        scene_prompt_hook = (GAME_DIR / "useScenePromptActions.js").read_text(encoding="utf-8")
        standalone_image_hook = (GAME_DIR / "useStandaloneImageGenerationActions.js").read_text(encoding="utf-8")

        self.assertIn("模型服务当前繁忙，请稍后重试。", helpers)
        self.assertIn("模型服务当前繁忙，请稍后重试。", game_page)
        self.assertNotIn("切换到更快", game_page)
        self.assertNotIn("切换模型", scene_prompt_hook)
        self.assertNotIn("切换模型", standalone_image_hook)
        self.assertNotIn("setTimeout(resolve, 1500)", game_page)

    def test_media_deletion_waits_for_persistence_success(self):
        game_page = (GAME_DIR / "GameVideoPage.jsx").read_text(encoding="utf-8")
        media_hook = (GAME_DIR / "useMediaResourceActions.js").read_text(encoding="utf-8")
        tab_persistence_hook = (GAME_DIR / "useWorkbenchTabPersistence.js").read_text(encoding="utf-8")
        scene_video_history_hook = (GAME_DIR / "useSceneVideoHistoryActions.js").read_text(encoding="utf-8")
        scene_image_hook = (GAME_DIR / "useSceneImageGenerationActions.js").read_text(encoding="utf-8")
        standalone_image_hook = (GAME_DIR / "useStandaloneImageGenerationActions.js").read_text(encoding="utf-8")
        scene_media_hook = (GAME_DIR / "useSceneMediaActions.js").read_text(encoding="utf-8")

        self.assertIn("pendingDeleteEntriesRef", media_hook)
        self.assertIn("flushDeletePromiseRef", media_hook)
        self.assertIn("markQueuedServerFilesReady", media_hook)
        self.assertIn("flushQueuedServerFileDeletes", media_hook)
        self.assertIn("deleteServerFilesAfterSave", media_hook)
        self.assertIn("onSaveSuccess: flushQueuedServerFileDeletes", game_page)
        self.assertIn("if (token !== latestSaveTokenRef.current)", (GAME_DIR / "useSceneAutosave.js").read_text(encoding="utf-8"))
        self.assertIn("return runImmediateSceneSave(nextGen, nextRepl", game_page)
        self.assertIn("return runImmediateSceneSave(genScenes, replScenes", tab_persistence_hook)
        self.assertIn("deleteServerFilesAfterSave(removed", scene_video_history_hook)
        self.assertIn("deleteServerFilesAfterSave(removed", scene_image_hook)
        self.assertIn("deleteServerFilesAfterSave(removed", standalone_image_hook)
        self.assertIn("deleteServerFilesAfterSave(removed", scene_media_hook)

    def test_task_polling_uses_visibility_jitter_and_backoff(self):
        task_polling_hook = (GAME_DIR / "useGameTaskPolling.js").read_text(encoding="utf-8")

        self.assertIn("visibilitychange", task_polling_hook)
        self.assertIn("hiddenIntervalMs = 30000", task_polling_hook)
        self.assertIn("jitterMs = 750", task_polling_hook)
        self.assertIn("maxBackoffMs = 30000", task_polling_hook)
        self.assertIn("nextVisiblePollDelay", task_polling_hook)
        self.assertNotIn("setInterval", task_polling_hook)

    def test_media_info_lookups_are_queued_and_visibility_aware(self):
        media_hook = (GAME_DIR / "useMediaResourceActions.js").read_text(encoding="utf-8")
        game_page = (GAME_DIR / "GameVideoPage.jsx").read_text(encoding="utf-8")

        self.assertIn("MEDIA_INFO_MAX_CONCURRENT = 1", media_hook)
        self.assertIn("durationLookupQueueRef", media_hook)
        self.assertIn("visibilitychange", media_hook)
        self.assertIn("/api/game/media_info", media_hook)
        self.assertIn("activeTab !== 'generate'", game_page)
        self.assertIn("activeTab === 'replace'", game_page)
        self.assertIn("activeTab === 'reverse'", game_page)

    def test_autosave_skips_unchanged_payloads(self):
        autosave_hook = (GAME_DIR / "useSceneAutosave.js").read_text(encoding="utf-8")

        self.assertIn("lastSavedPayloadRef", autosave_hook)
        self.assertIn("JSON.stringify(payload)", autosave_hook)
        self.assertIn("unchanged: true", autosave_hook)
        self.assertIn("setSaveStatus('idle')", autosave_hook)

    def test_workbench_tab_state_owns_saved_tab_slices(self):
        game_page = (GAME_DIR / "GameVideoPage.jsx").read_text(encoding="utf-8")
        tab_state_hook = (GAME_DIR / "useWorkbenchTabState.js").read_text(encoding="utf-8")

        self.assertNotIn("const [replCharImage", game_page)
        self.assertNotIn("const [imgGenPrompt", game_page)
        self.assertNotIn("const [reverseVideoUrl", game_page)
        self.assertIn("const [replCharImage, setReplCharImage] = useState(null)", tab_state_hook)
        self.assertIn("const [imgGenPrompt, setImgGenPrompt] = useState('')", tab_state_hook)
        self.assertIn("const [reverseVideoUrl, setReverseVideoUrl] = useState('')", tab_state_hook)
        self.assertIn("replaceVideoSetters", tab_state_hook)
        self.assertIn("standaloneImageSetters", tab_state_hook)
        self.assertIn("videoReverseSetters", tab_state_hook)

    def test_workbench_tab_state_fields_stay_in_sync(self):
        tab_state_hook = (GAME_DIR / "useWorkbenchTabState.js").read_text(encoding="utf-8")
        helpers = (GAME_DIR / "gameVideoPageHelpers.js").read_text(encoding="utf-8")
        fields = {
            "replaceVideo": [
                "replHistory",
                "replCharImage",
                "replRefVideo",
                "replRefVideoDurationSeconds",
                "replPrompt",
                "replProvider",
                "replWanMode",
                "replWanCheckImage",
                "replVideoResolution",
                "replVideoUrl",
                "replTaskId",
                "replStatus",
                "replError",
                "replStartTime",
            ],
            "standaloneImage": [
                "imgGenHistory",
                "imgGenPrompt",
                "imgGenPromptModel",
                "imgGenModel",
                "imgGenProvider",
                "imgGenRefImages",
                "imgGenEditMode",
                "imgGenAspectRatio",
                "imgGenQuality",
            ],
            "videoReverse": [
                "reverseHistory",
                "reverseVideoUrl",
                "reverseVideoDurationSeconds",
                "reverseModel",
                "reverseResult",
            ],
        }

        for group, group_fields in fields.items():
            with self.subTest(group=group):
                self.assertIn(f"{group}:", tab_state_hook)
            for field in group_fields:
                with self.subTest(field=field):
                    setter = f"set{field[0].upper()}{field[1:]}"
                    self.assertIn(f"const [{field}, {setter}]", tab_state_hook)
                    self.assertIn(f"{setter}(", tab_state_hook)
                    self.assertIn(f"{field}:", helpers)

    def test_workbench_tab_state_remains_side_effect_free(self):
        tab_state_hook = (GAME_DIR / "useWorkbenchTabState.js").read_text(encoding="utf-8")

        self.assertNotIn("/api/game/", tab_state_hook)
        self.assertNotIn("api.", tab_state_hook)
        self.assertNotIn("localStorage", tab_state_hook)
        self.assertNotIn("sessionStorage", tab_state_hook)
        self.assertNotIn("writeWorkbenchCache", tab_state_hook)
        self.assertNotIn("setInterval", tab_state_hook)
        self.assertNotIn("setTimeout", tab_state_hook)
        self.assertNotIn("document.", tab_state_hook)
        self.assertNotIn("navigator.clipboard", tab_state_hook)

    def test_project_loader_owns_project_hydration_boundary(self):
        project_loader = (GAME_DIR / "useProjectLoader.js").read_text(encoding="utf-8")
        project_actions = (GAME_DIR / "useProjectActions.js").read_text(encoding="utf-8")

        self.assertIn("/api/game/projects/${project.id}/scenes", project_loader)
        self.assertIn("clearAllTaskPolling()", project_loader)
        self.assertIn("beginProjectHydration(project.id)", project_loader)
        self.assertIn("finishProjectHydration()", project_loader)
        self.assertIn("applyTabState(", project_loader)
        self.assertIn("resumeSceneTaskPolling(", project_loader)
        self.assertIn("resumeReplaceTaskPolling(", project_loader)
        self.assertNotIn("/scenes", project_actions)
        self.assertNotIn("clearAllTaskPolling", project_actions)
        self.assertNotIn("beginProjectHydration", project_actions)
        self.assertNotIn("finishProjectHydration", project_actions)

    def test_project_actions_only_touch_project_crud_endpoints(self):
        project_actions = (GAME_DIR / "useProjectActions.js").read_text(encoding="utf-8")

        self.assertIn("/api/game/projects", project_actions)
        self.assertNotIn("/api/game/upload", project_actions)
        self.assertNotIn("/api/game/generate_", project_actions)
        self.assertNotIn("/api/game/replace_video", project_actions)
        self.assertNotIn("/api/game/settings", project_actions)
        self.assertNotIn("/api/game/video_models", project_actions)
        self.assertNotIn("/api/game/image_models", project_actions)

    def test_game_page_keeps_project_orchestration_wiring(self):
        game_page = (GAME_DIR / "GameVideoPage.jsx").read_text(encoding="utf-8")

        self.assertIn("const { openProject } = useProjectLoader({", game_page)
        self.assertIn("} = useProjectActions({", game_page)
        self.assertIn("openProject,", game_page)
        self.assertIn("onOpenProject={openProject}", game_page)
        self.assertIn("onCreateProject={createProject}", game_page)
        self.assertIn("onDeleteProject={deleteProject}", game_page)
        self.assertIn("onSaveProjectRename={saveProjectRename}", game_page)

    def test_scene_pair_helpers_are_initialized_before_hook_consumers(self):
        game_page = (GAME_DIR / "GameVideoPage.jsx").read_text(encoding="utf-8")

        helper_index = game_page.index("const makeInitialScenePair = useCallback(")
        bootstrap_index = game_page.index("} = useWorkbenchBootstrap({")
        loader_index = game_page.index("const { openProject } = useProjectLoader({")

        self.assertLess(helper_index, bootstrap_index)
        self.assertLess(helper_index, loader_index)

    def test_replace_video_hook_only_touches_replace_endpoint(self):
        replace_video_hook = (GAME_DIR / "useReplaceVideoActions.js").read_text(encoding="utf-8")

        self.assertIn("/api/game/replace_video", replace_video_hook)
        self.assertNotIn("/api/game/generate_video", replace_video_hook)
        self.assertNotIn("/api/game/generate_image", replace_video_hook)
        self.assertNotIn("/api/game/analyze_video", replace_video_hook)
        self.assertNotIn("/api/game/analyze_prompt", replace_video_hook)
        self.assertNotIn("/api/game/refresh_prompt", replace_video_hook)

    def test_replace_panel_actions_hook_does_not_touch_api_endpoints(self):
        replace_panel_hook = (GAME_DIR / "useReplaceVideoPanelActions.js").read_text(encoding="utf-8")

        self.assertNotIn("/api/game/", replace_panel_hook)
        self.assertNotIn("api.", replace_panel_hook)


if __name__ == "__main__":
    unittest.main()
