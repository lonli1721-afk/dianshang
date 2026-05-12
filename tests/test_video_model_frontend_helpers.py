from __future__ import annotations

import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VideoModelFrontendHelperTests(unittest.TestCase):
    maxDiff = None

    def test_video_model_helpers_follow_catalog_capabilities(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required to import frontend model helpers")

        script = textwrap.dedent(
            """
            import assert from 'node:assert/strict';
            import { FALLBACK_VIDEO_MODELS } from './src/pages/game/gameVideoConstants.js';
            import {
              formatProviderVideoCacheError,
              isProviderVideoCacheError,
            } from './src/pages/game/gameVideoPageHelpers.js';
            import {
              getVideoGenerationBlockReasonForModel,
              getVideoMaxReferenceVideos,
              getVideoReferenceDurationIssue,
              getReplaceProviderSpec,
              getReplaceReferenceDurationIssue,
              getReplaceVideoBlockReason,
              isVideoModeSupported,
              normalizeVideoModeForModel,
            } from './src/pages/game/gameVideoModelUtils.js';

            const byId = Object.fromEntries(FALLBACK_VIDEO_MODELS.map(item => [item.id, item]));
            const cacheError = '视频任务已完成，但结果视频保存到本地失败：ConnectTimeout。请重新生成。';

            assert.equal(isProviderVideoCacheError(cacheError), true);
            assert.equal(isProviderVideoCacheError('上游生成失败：InvalidParameter'), false);
            assert.equal(
              formatProviderVideoCacheError(cacheError),
              '视频任务已完成，但结果视频保存到本地失败：ConnectTimeout。可先点击“重新拉取结果”。',
            );
            assert.equal(formatProviderVideoCacheError('上游生成失败：InvalidParameter'), '上游生成失败：InvalidParameter');

            const scene = (overrides = {}) => ({
              prompt: '测试视频提示词',
              videoMode: 'generate',
              duration: 5,
              videoResolution: '720p',
              charImages: [],
              sceneImages: [],
              refVideoUrl: '',
              refVideoDurationSeconds: null,
              advancedRefVideos: [],
              ...overrides,
            });

            const seedance = byId['seedance-2.0'];
            assert.equal(isVideoModeSupported(seedance, 'reference_video'), true);
            assert.equal(isVideoModeSupported(seedance, 'advanced_video'), true);
            assert.match(getVideoReferenceDurationIssue(16, seedance), /15\\.2/);
            assert.match(getVideoReferenceDurationIssue(null, seedance), /时长暂未检测完成/);

            const seedance15 = byId['seedance-1.5-pro'];
            assert.equal(isVideoModeSupported(seedance15, 'reference_video'), false);
            assert.equal(normalizeVideoModeForModel('advanced_video', seedance15), 'generate');
            assert.match(
              getVideoGenerationBlockReasonForModel(seedance15, scene({ videoMode: 'reference_video', refVideoUrl: '/api/files/a.mp4' })),
              /不支持参考视频生成/,
            );

            const vidu = byId['viduq3-turbo'];
            assert.equal(getVideoGenerationBlockReasonForModel(vidu, scene({ charImages: [{ url: 'a' }] })), '');
            assert.match(
              getVideoGenerationBlockReasonForModel(vidu, scene({ charImages: [{ url: 'a' }, { url: 'b' }] })),
              /最多支持 1 张参考图/,
            );

            const happyI2v = byId['happyhorse-1.0-i2v'];
            assert.match(getVideoGenerationBlockReasonForModel(happyI2v, scene()), /需要至少 1 张参考图/);
            assert.match(
              getVideoGenerationBlockReasonForModel(happyI2v, scene({ charImages: [{ url: 'a' }, { url: 'b' }] })),
              /最多支持 1 张参考图/,
            );

            const happyR2v = byId['happyhorse-1.0-r2v'];
            assert.match(getVideoGenerationBlockReasonForModel(happyR2v, scene()), /需要至少 1 张参考图/);
            assert.equal(getVideoGenerationBlockReasonForModel(happyR2v, scene({ charImages: [{ url: 'a' }] })), '');

            const happyEdit = byId['happyhorse-1.0-video-edit'];
            assert.equal(isVideoModeSupported(happyEdit, 'generate'), false);
            assert.equal(normalizeVideoModeForModel('generate', happyEdit), 'reference_video');
            assert.equal(getVideoMaxReferenceVideos(happyEdit), 1);
            assert.match(getVideoReferenceDurationIssue(2, happyEdit), /低于 HappyHorse 3 秒/);
            assert.match(getVideoReferenceDurationIssue(61, happyEdit), /已超过 HappyHorse 60 秒/);
            assert.match(
              getVideoGenerationBlockReasonForModel(happyEdit, scene({
                videoMode: 'advanced_video',
                advancedRefVideos: [{ url: 'a', durationSeconds: 5 }, { url: 'b', durationSeconds: 5 }],
              })),
              /最多支持 1 个参考视频/,
            );

            const wanReplace = getReplaceProviderSpec('wan');
            assert.equal(wanReplace.label, '万相视频换人');
            assert.equal(wanReplace.uploadHint, '支持 mp4、mov、avi；万相要求 2-30 秒');
            assert.equal(wanReplace.actionLabel, '开始视频换人');
            assert.equal(wanReplace.supports_check_image, true);
            assert.equal(wanReplace.wan_modes.length, 2);
            assert.match(getReplaceReferenceDurationIssue(1.9, 'wan'), /低于 万相 2 秒/);
            assert.match(getReplaceReferenceDurationIssue(31, 'wan'), /已超过 万相 30 秒/);

            const seedanceReplace = getReplaceProviderSpec('jimeng');
            assert.equal(seedanceReplace.label, 'Seedance 动作模仿');
            assert.equal(seedanceReplace.supports_prompt, true);
            assert.equal(seedanceReplace.supports_resolution, true);
            assert.equal(seedanceReplace.actionLabel, '开始动作模仿');
            assert.match(getReplaceReferenceDurationIssue(16, 'jimeng'), /已超过 Seedance 15\\.2 秒/);
            assert.match(getReplaceReferenceDurationIssue(null, 'jimeng'), /Seedance参考视频真实时长暂未检测完成/);

            assert.equal(getReplaceVideoBlockReason('wan', { charImage: null, refVideo: '/api/files/a.mp4' }), '请先上传替换角色图片');
            assert.equal(getReplaceVideoBlockReason('wan', { charImage: { url: 'a' }, refVideo: '' }), '请先上传参考视频');
            assert.equal(
              getReplaceVideoBlockReason('wan', { charImage: { url: 'a' }, refVideo: '/api/files/a.mp4', refVideoDurationSeconds: 10 }),
              '',
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
