from __future__ import annotations

import argparse
import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_task_auto_heal_module():
    spec = importlib.util.spec_from_file_location(
        "task_auto_heal_dry_run",
        ROOT / "deploy" / "task-auto-heal-dry-run.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeProbeModule:
    def __init__(self, payload: dict):
        self.payload = payload
        self.received_args = None

    def build_parser(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--data-dir", type=Path)
        parser.add_argument("--backup-dir", type=Path)
        parser.add_argument("--stale-hours", type=float)
        parser.add_argument("--since-hours", type=float)
        parser.add_argument("--sample-limit", type=int)
        parser.add_argument("--prompt-preview-chars", type=int)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--concurrency", type=int)
        parser.add_argument("--task-id", action="append", default=[])
        parser.add_argument("--include-failed", action="store_true")
        return parser

    async def run_probe(self, args):
        self.received_args = args
        return self.payload


def make_probe_payload(probes: list[dict], *, db_errors: list[dict] | None = None) -> dict:
    return {
        "created_at": "2026-05-08T00:00:00+00:00",
        "candidate_count": len(probes),
        "candidate_counts": {"seedance": len(probes)},
        "probe_count": len(probes),
        "api_key_present_by_provider": {"seedance": True},
        "audit_summary": {
            "stale_processing_count": len(probes),
            "db_errors": db_errors or [],
        },
        "probes": probes,
        "recommendations": ["probe ok"],
    }


def make_args(**overrides):
    values = {
        "data_dir": Path("/tmp/data"),
        "backup_dir": Path("/tmp/backups"),
        "stale_hours": 2,
        "since_hours": 24,
        "sample_limit": 50,
        "prompt_preview_chars": 120,
        "limit": 10,
        "concurrency": 1,
        "task_id": [],
        "include_failed": False,
        "max_auto_candidates": 5,
        "json_report": None,
        "report_dir": None,
        "retention_hours": 72,
        "keep_latest_count": 288,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TaskAutoHealDryRunTests(unittest.TestCase):
    def test_completed_processing_task_with_video_becomes_auto_candidate(self):
        module = load_task_auto_heal_module()
        probe = FakeProbeModule(make_probe_payload([{
            "task_id": "task-1",
            "external_task_id": "external-1",
            "username": "alice",
            "provider": "jimeng",
            "model": "seedance",
            "local_status": "processing",
            "provider_status": "completed",
            "has_provider_video_url": True,
            "provider_error": "",
            "recommended_action": module.AUTO_ACTION,
        }]))
        module.load_task_state_probe_module = lambda: probe

        payload = module.build_auto_heal_report(make_args())

        self.assertTrue(payload["readonly"])
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["mutates_database"])
        self.assertFalse(payload["downloads_media"])
        self.assertFalse(payload["repairs_tasks"])
        self.assertEqual(payload["auto_repair_candidate_count"], 1)
        self.assertEqual(payload["auto_repair_candidates"][0]["task_id"], "task-1")
        self.assertEqual(payload["auto_repair_candidates"][0]["category"], "auto_repair_candidate")

    def test_failed_or_probe_error_tasks_require_manual_review(self):
        module = load_task_auto_heal_module()
        probe = FakeProbeModule(make_probe_payload([
            {
                "task_id": "task-failed",
                "external_task_id": "external-failed",
                "local_status": "processing",
                "provider_status": "failed",
                "has_provider_video_url": False,
                "provider_error": "",
                "recommended_action": "can_repair_to_failed_after_review",
            },
            {
                "task_id": "task-probe-error",
                "external_task_id": "external-probe-error",
                "local_status": "processing",
                "provider_status": "probe_error",
                "has_provider_video_url": False,
                "provider_error": "timeout",
                "recommended_action": "do_not_modify_until_probe_succeeds",
            },
        ]))
        module.load_task_state_probe_module = lambda: probe

        payload = module.build_auto_heal_report(make_args())

        self.assertEqual(payload["auto_repair_candidate_count"], 0)
        self.assertEqual(payload["candidate_counts"]["manual_review"], 2)

    def test_non_processing_completed_task_is_not_auto_candidate(self):
        module = load_task_auto_heal_module()
        probe = FakeProbeModule(make_probe_payload([{
            "task_id": "task-1",
            "external_task_id": "external-1",
            "local_status": "failed",
            "provider_status": "completed",
            "has_provider_video_url": True,
            "provider_error": "",
            "recommended_action": module.AUTO_ACTION,
        }]))
        module.load_task_state_probe_module = lambda: probe

        payload = module.build_auto_heal_report(make_args())

        self.assertEqual(payload["auto_repair_candidate_count"], 0)
        self.assertEqual(payload["candidate_counts"]["manual_review"], 1)

    def test_include_failed_and_task_ids_are_forwarded_to_probe_args(self):
        module = load_task_auto_heal_module()
        probe = FakeProbeModule(make_probe_payload([]))
        module.load_task_state_probe_module = lambda: probe

        module.build_auto_heal_report(make_args(task_id=["task-1", "task-2"], include_failed=True))

        self.assertTrue(probe.received_args.include_failed)
        self.assertEqual(probe.received_args.task_id, ["task-1", "task-2"])

    def test_write_report_dir_keeps_latest_and_cleans_only_auto_heal_reports(self):
        module = load_task_auto_heal_module()
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            old_json = report_dir / "task-auto-heal-dry-run-20260501-010000.json"
            old_txt = report_dir / "task-auto-heal-dry-run-20260501-010000.txt"
            latest = report_dir / "task-auto-heal-dry-run-latest.json"
            unrelated = report_dir / "task-stale-watch-20260501-010000.json"
            for path in (old_json, old_txt, latest, unrelated):
                path.write_text("x", encoding="utf-8")
            old_ts = time.time() - 10 * 24 * 3600
            for path in (old_json, old_txt, latest, unrelated):
                os.utime(path, (old_ts, old_ts))
            payload = {
                "readonly": True,
                "dry_run": True,
                "calls_provider_api": True,
                "probe_count": 0,
                "auto_repair_candidate_count": 0,
                "candidate_counts": {},
                "db_errors": [],
                "recommendations": ["ok"],
            }

            outputs = module.write_report_dir(report_dir, payload, retention_hours=24, keep_latest_count=0)

            self.assertTrue(Path(outputs["json_report"]).exists())
            self.assertTrue(Path(outputs["text_report"]).exists())
            self.assertTrue((report_dir / "task-auto-heal-dry-run-latest.json").exists())
            self.assertTrue((report_dir / "task-auto-heal-dry-run-latest.txt").exists())
            self.assertFalse(old_json.exists())
            self.assertFalse(old_txt.exists())
            self.assertTrue(unrelated.exists())

    def test_script_has_no_execute_or_media_download_path(self):
        script = (ROOT / "deploy" / "task-auto-heal-dry-run.py").read_text("utf-8")

        self.assertNotIn("add_argument(\"--execute\"", script)
        self.assertNotIn("task-state-repair.py", script)
        self.assertNotIn("urlretrieve", script)
        self.assertNotIn(".backup(", script)
        self.assertNotIn("sqlite3.connect", script)


if __name__ == "__main__":
    unittest.main()
