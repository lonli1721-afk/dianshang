from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import video_model_registry  # noqa: E402


class VideoModelFrontendParityTests(unittest.TestCase):
    maxDiff = None

    def test_frontend_fallback_models_match_backend_registry(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required to import frontend model constants")

        script = (
            "import { FALLBACK_VIDEO_MODELS } from './src/pages/game/gameVideoConstants.js';"
            "console.log(JSON.stringify(FALLBACK_VIDEO_MODELS));"
        )
        completed = subprocess.run(
            [node, "--input-type=module", "-e", script],
            cwd=ROOT / "react-ui",
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        frontend_models = json.loads(completed.stdout)
        backend_models = video_model_registry.get_all_video_model_specs()
        self.assertEqual(frontend_models, backend_models)


if __name__ == "__main__":
    unittest.main()
