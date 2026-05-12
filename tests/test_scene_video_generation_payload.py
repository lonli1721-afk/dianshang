from __future__ import annotations

import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SceneVideoGenerationPayloadTests(unittest.TestCase):
    def test_payload_shape_matches_generate_video_contract(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required to import frontend payload helper")

        script = textwrap.dedent(
            """
            import assert from 'node:assert/strict';
            import { buildSceneVideoGenerationPayload } from './src/pages/game/sceneVideoGenerationPayload.js';

            const model = {
              id: 'seedance-2.0',
              supported_resolutions: ['720p', '1080p'],
              default_resolution: '720p',
            };
            const baseScene = {
              prompt: '镜头从树林推近主角',
              provider: 'jimeng',
              model: 'seedance-2.0',
              duration: 5,
              aspectRatio: '9:16',
              videoResolution: '1080p',
              charImages: [{ url: '/api/files/char.png' }],
              sceneImages: [{ url: '/api/files/scene.png' }],
              refVideoUrl: '/api/files/ref.mp4',
              advancedRefVideos: [{ url: '/api/files/adv-a.mp4' }, { url: '/api/files/adv-b.mp4' }],
            };

            assert.deepEqual(
              buildSceneVideoGenerationPayload({
                currentProjectId: 'project-1',
                scene: { ...baseScene, videoMode: 'generate' },
                selectedModel: model,
                provider: 'jimeng',
              }),
              {
                project_id: 'project-1',
                prompt: '镜头从树林推近主角',
                provider: 'jimeng',
                model: 'seedance-2.0',
                duration: 5,
                aspect_ratio: '9:16',
                resolution: '1080p',
                character_refs: ['/api/files/char.png'],
                scene_refs: ['/api/files/scene.png'],
                reference_video_url: '',
                advanced_reference_videos: [],
              },
            );

            assert.deepEqual(
              buildSceneVideoGenerationPayload({
                currentProjectId: '',
                scene: { ...baseScene, videoMode: 'reference_video' },
                selectedModel: model,
                provider: 'jimeng',
              }).reference_video_url,
              '/api/files/ref.mp4',
            );

            assert.deepEqual(
              buildSceneVideoGenerationPayload({
                currentProjectId: 'project-1',
                scene: { ...baseScene, videoMode: 'advanced_video' },
                selectedModel: model,
                provider: 'jimeng',
              }).advanced_reference_videos,
              ['/api/files/adv-a.mp4', '/api/files/adv-b.mp4'],
            );
            """
        )

        subprocess.run(
            [node, "--input-type=module", "-e", script],
            cwd=ROOT / "react-ui",
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )


if __name__ == "__main__":
    unittest.main()
