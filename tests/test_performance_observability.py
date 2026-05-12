from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_perf_module():
    spec = importlib.util.spec_from_file_location("performance_observability", ROOT / "server" / "performance_observability.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_report_module():
    spec = importlib.util.spec_from_file_location("performance_report", ROOT / "deploy" / "performance-report.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PerformanceObservabilityTests(unittest.TestCase):
    def test_path_categories_match_slow_workflow_buckets(self):
        perf = load_perf_module()

        self.assertEqual(perf.performance_category("GET", "/api/game/projects/abc/scenes"), "project_loading")
        self.assertEqual(perf.performance_category("GET", "/api/files/demo.mp4?token=secret"), "media_preview")
        self.assertEqual(perf.performance_category("POST", "/api/game/tasks/status/batch"), "task_polling")
        self.assertEqual(perf.performance_category("POST", "/api/game/analyze_video"), "model_request")
        self.assertEqual(perf.performance_category("POST", "/api/viral/analyses/a1/plans"), "model_request")

    def test_perf_log_is_sanitized_and_parseable(self):
        perf = load_perf_module()

        line = perf.format_perf_log("GET", "/api/files/demo.mp4?token=secret", 200, 1234.56, 800)
        parsed = perf.parse_perf_log_line(line)

        self.assertIn("/api/files/{file}", line)
        self.assertNotIn("secret", line)
        self.assertEqual(parsed["category"], "media_preview")
        self.assertEqual(parsed["duration_ms"], 1234.6)

    def test_summary_groups_by_category_and_route(self):
        perf = load_perf_module()
        rows = [
            perf.parse_perf_log_line(perf.format_perf_log("GET", "/api/game/projects/a/scenes", 200, 900, 800)),
            perf.parse_perf_log_line(perf.format_perf_log("POST", "/api/game/analyze_video", 200, 2500, 800)),
        ]

        summary = perf.summarize_perf_rows(rows)

        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["by_category"][0]["key"], "model_request")
        self.assertEqual(summary["top_routes"][0]["key"], "POST /api/game/analyze_video")

    def test_performance_report_is_readonly_and_handles_empty_logs(self):
        report_module = load_report_module()
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "app.log"
            log_file.write_text("INFO normal line\n", encoding="utf-8")
            args = report_module.build_parser().parse_args(["--log-file", str(log_file)])

            payload = report_module.build_report(args)

        self.assertTrue(payload["readonly"])
        self.assertFalse(payload["mutates_database"])
        self.assertEqual(payload["summary"]["sample_count"], 0)
        self.assertIn("尚未采集到慢请求样本", payload["recommendations"][0])

    def test_request_volume_summary_sanitizes_routes(self):
        perf = load_perf_module()
        rows = [
            perf.parse_access_log_line('INFO:     1.2.3.4:0 - "POST /api/game/tasks/status/batch HTTP/1.1" 200 OK'),
            perf.parse_access_log_line('INFO:     1.2.3.4:0 - "PUT /api/game/projects/abc123/scenes HTTP/1.1" 200 OK'),
            perf.parse_access_log_line('INFO:     1.2.3.4:0 - "GET /api/files/demo.mp4?token=secret HTTP/1.1" 206 Partial Content'),
        ]

        summary = perf.summarize_access_rows(rows)

        self.assertEqual(summary["sample_count"], 3)
        route_keys = [row["key"] for row in summary["top_routes"]]
        self.assertIn("POST /api/game/tasks/status/batch", route_keys)
        self.assertIn("PUT /api/game/projects/{project_id}/scenes", route_keys)
        self.assertIn("GET /api/files/{file}", route_keys)
        self.assertNotIn("secret", str(summary))


if __name__ == "__main__":
    unittest.main()
