from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_execute_module():
    return load_module("media_cleanup_execute", ROOT / "deploy" / "media-cleanup-execute.py")


def load_preflight_module():
    return load_module("media_cleanup_preflight", ROOT / "deploy" / "media-cleanup-preflight.py")


def load_cleanup_plan_module():
    return load_module("media_cleanup_plan", ROOT / "deploy" / "media-cleanup-plan.py")


def write_old_file(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    ts = time.time() - 72 * 3600
    os.utime(path, (ts, ts))
    return path


def plan_args(data_dir: Path):
    return SimpleNamespace(
        data_dir=data_dir,
        json_report=None,
        min_age_hours=24.0,
        candidate_limit=0,
        sample_limit=50,
        reference_sample_limit=3,
        include_all_tables=False,
    )


def preflight_args(allowlist: Path, data_dir: Path):
    return SimpleNamespace(
        allowlist=allowlist,
        data_dir=data_dir,
        json_report=None,
        min_age_hours=24.0,
        include_all_tables=False,
    )


def execute_args(
    allowlist: Path,
    preflight_report: Path,
    data_dir: Path,
    expected_count: int,
    expected_logical_bytes: int,
    **overrides,
):
    values = {
        "allowlist": allowlist,
        "preflight_report": preflight_report,
        "data_dir": data_dir,
        "json_report": None,
        "expected_count": expected_count,
        "expected_logical_bytes": expected_logical_bytes,
        "min_age_hours": 24.0,
        "include_all_tables": False,
        "execute": False,
        "confirm_token": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def allowlist_row_from_candidate(candidate: dict, review_status: str = "approved") -> dict:
    return {
        "candidate_id": candidate["candidate_id"],
        "path": candidate["path"],
        "filename": candidate.get("filename", ""),
        "scope": candidate.get("scope", ""),
        "user_id": candidate.get("user_id", ""),
        "size": candidate["size"],
        "mtime": candidate["mtime"],
        "age_hours": candidate["age_hours"],
        "reference_count": candidate["reference_count"],
        "reference_kinds": candidate.get("reference_kinds") or {},
        "expected": {
            "size": candidate["size"],
            "mtime": candidate["mtime"],
            "reference_class": "unreferenced",
            "path": candidate["path"],
        },
        "review_status": review_status,
    }


def write_allowlist(path: Path, rows: list[dict]) -> Path:
    payload = {
        "action": "media_cleanup_allowlist",
        "dry_run": True,
        "deletion_enabled": False,
        "review_required": True,
        "created_at": "2026-05-05T00:00:00+08:00",
        "selection": {
            "min_age_hours": 24.0,
            "max_count": 20,
            "max_bytes": 512 * 1024 * 1024,
            "sort": "size-desc",
            "fill_gaps": False,
            "scope": ["global", "user"],
        },
        "preflight_errors": [],
        "selected_count": len(rows),
        "selected_logical_bytes": sum(int(row.get("size") or 0) for row in rows),
        "allowlist": rows,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def make_allowlist_and_preflight(tmp_path: Path, review_status: str = "approved", file_count: int = 1):
    cleanup_plan = load_cleanup_plan_module()
    preflight = load_preflight_module()
    media_paths = []
    for index in range(file_count):
        media_paths.append(write_old_file(tmp_path / "files" / f"orphan-{index}.mp4", f"orphan-{index}".encode()))
    plan = cleanup_plan.build_plan(plan_args(tmp_path))
    rows = [allowlist_row_from_candidate(candidate, review_status=review_status) for candidate in plan["candidates"]]
    allowlist = write_allowlist(tmp_path / "allowlist.json", rows)
    preflight_payload = preflight.build_preflight(preflight_args(allowlist, tmp_path))
    preflight_report = tmp_path / "preflight.json"
    preflight_report.write_text(json.dumps(preflight_payload), encoding="utf-8")
    return media_paths, allowlist, preflight_report, preflight_payload


class MediaCleanupExecuteTests(unittest.TestCase):
    def test_dry_run_does_not_delete_approved_files(self):
        execute = load_execute_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            media_paths, allowlist, preflight_report, preflight_payload = make_allowlist_and_preflight(tmp_path)

            payload = execute.build_execution_report(
                execute_args(
                    allowlist,
                    preflight_report,
                    tmp_path,
                    expected_count=preflight_payload["verified_count"],
                    expected_logical_bytes=preflight_payload["verified_logical_bytes"],
                )
            )

            self.assertTrue(media_paths[0].exists())
            self.assertTrue(payload["dry_run"])
            self.assertTrue(payload["can_execute"])
            self.assertFalse(payload["executed"])
            self.assertEqual(payload["would_delete_count"], 1)
            self.assertEqual(payload["deleted_count"], 0)

    def test_pending_allowlist_blocks_execution(self):
        execute = load_execute_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            media_paths, allowlist, preflight_report, preflight_payload = make_allowlist_and_preflight(tmp_path, review_status="pending")
            token = execute.confirmation_token(preflight_payload["verified_count"], preflight_payload["verified_logical_bytes"])

            payload = execute.build_execution_report(
                execute_args(
                    allowlist,
                    preflight_report,
                    tmp_path,
                    expected_count=preflight_payload["verified_count"],
                    expected_logical_bytes=preflight_payload["verified_logical_bytes"],
                    execute=True,
                    confirm_token=token,
                )
            )

            self.assertTrue(media_paths[0].exists())
            self.assertFalse(payload["can_execute"])
            self.assertFalse(payload["executed"])
            self.assertIn("current_preflight_not_ready_for_execution", payload["guard_errors"])
            self.assertIn("human_review_required", payload["guard_errors"])
            self.assertEqual(payload["items"][0]["status"], "verified_but_blocked_by_guards")

    def test_execute_requires_confirmation_token(self):
        execute = load_execute_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            media_paths, allowlist, preflight_report, preflight_payload = make_allowlist_and_preflight(tmp_path)

            payload = execute.build_execution_report(
                execute_args(
                    allowlist,
                    preflight_report,
                    tmp_path,
                    expected_count=preflight_payload["verified_count"],
                    expected_logical_bytes=preflight_payload["verified_logical_bytes"],
                    execute=True,
                    confirm_token="wrong-token",
                )
            )

            self.assertTrue(media_paths[0].exists())
            self.assertFalse(payload["can_execute"])
            self.assertIn("invalid_confirmation_token", payload["guard_errors"])

    def test_execute_deletes_approved_files_with_exact_guards(self):
        execute = load_execute_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            media_paths, allowlist, preflight_report, preflight_payload = make_allowlist_and_preflight(tmp_path)
            token = execute.confirmation_token(preflight_payload["verified_count"], preflight_payload["verified_logical_bytes"])

            payload = execute.build_execution_report(
                execute_args(
                    allowlist,
                    preflight_report,
                    tmp_path,
                    expected_count=preflight_payload["verified_count"],
                    expected_logical_bytes=preflight_payload["verified_logical_bytes"],
                    execute=True,
                    confirm_token=token,
                )
            )

            self.assertFalse(media_paths[0].exists())
            self.assertTrue(payload["executed"])
            self.assertEqual(payload["deleted_count"], 1)
            self.assertEqual(payload["deleted_logical_bytes"], preflight_payload["verified_logical_bytes"])

    def test_size_change_blocks_before_any_delete(self):
        execute = load_execute_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            media_paths, allowlist, preflight_report, preflight_payload = make_allowlist_and_preflight(tmp_path, file_count=2)
            media_paths[0].write_bytes(b"changed")
            ts = time.time() - 72 * 3600
            os.utime(media_paths[0], (ts, ts))
            token = execute.confirmation_token(preflight_payload["verified_count"], preflight_payload["verified_logical_bytes"])

            payload = execute.build_execution_report(
                execute_args(
                    allowlist,
                    preflight_report,
                    tmp_path,
                    expected_count=preflight_payload["verified_count"],
                    expected_logical_bytes=preflight_payload["verified_logical_bytes"],
                    execute=True,
                    confirm_token=token,
                )
            )

            self.assertTrue(media_paths[0].exists())
            self.assertTrue(media_paths[1].exists())
            self.assertFalse(payload["can_execute"])
            self.assertEqual(payload["deleted_count"], 0)

    def test_expected_count_mismatch_blocks_execution(self):
        execute = load_execute_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            media_paths, allowlist, preflight_report, preflight_payload = make_allowlist_and_preflight(tmp_path)
            token = execute.confirmation_token(2, preflight_payload["verified_logical_bytes"])

            payload = execute.build_execution_report(
                execute_args(
                    allowlist,
                    preflight_report,
                    tmp_path,
                    expected_count=2,
                    expected_logical_bytes=preflight_payload["verified_logical_bytes"],
                    execute=True,
                    confirm_token=token,
                )
            )

            self.assertTrue(media_paths[0].exists())
            self.assertFalse(payload["can_execute"])
            self.assertIn("preflight_verified_count_mismatch", payload["input_preflight_errors"])
            self.assertIn("current_verified_count_mismatch", payload["guard_errors"])

    def test_static_safety_contracts(self):
        execute_source = (ROOT / "deploy" / "media-cleanup-execute.py").read_text(encoding="utf-8")
        plan_source = (ROOT / "deploy" / "media-cleanup-plan.py").read_text(encoding="utf-8")
        allowlist_source = (ROOT / "deploy" / "media-cleanup-allowlist.py").read_text(encoding="utf-8")
        preflight_source = (ROOT / "deploy" / "media-cleanup-preflight.py").read_text(encoding="utf-8")

        self.assertIn(".unlink(", execute_source)
        self.assertNotIn("rmtree(", execute_source)
        self.assertNotIn("os.remove", execute_source)
        self.assertNotIn("os.replace", execute_source)
        self.assertNotIn("os.link", execute_source)
        self.assertNotIn("DELETE FROM", execute_source)
        self.assertNotIn("UPDATE ", execute_source)
        self.assertNotIn("INSERT INTO", execute_source)
        self.assertNotIn("CREATE TABLE", execute_source)
        self.assertNotIn("DROP TABLE", execute_source)
        for source in (plan_source, allowlist_source, preflight_source):
            self.assertNotIn("--execute", source)
            self.assertNotIn(".unlink(", source)
            self.assertNotIn("rmtree(", source)
            self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()
