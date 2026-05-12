from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_allowlist_module():
    spec = importlib.util.spec_from_file_location("media_cleanup_allowlist", ROOT / "deploy" / "media-cleanup-allowlist.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def candidate(candidate_id: str, path: str, size: int, age_hours: float = 120, **overrides) -> dict:
    row = {
        "candidate_id": candidate_id,
        "filename": Path(path).name,
        "path": path,
        "scope": "global",
        "user_id": "",
        "size": size,
        "mtime": "2026-04-30T10:00:00+08:00",
        "age_hours": age_hours,
        "reference_count": 0,
        "reference_kinds": {},
        "recheck": {
            "path_exists": True,
            "regular_file": True,
            "symlink": False,
            "allowed_scope": True,
            "reference_class": "unreferenced",
        },
    }
    row.update(overrides)
    return row


def write_plan(path: Path, candidates: list[dict], **overrides) -> Path:
    payload = {
        "action": "media_cleanup_plan",
        "dry_run": True,
        "deletion_enabled": False,
        "created_at": "2026-05-04T23:00:00+08:00",
        "candidate_count": len(candidates),
        "estimated_reclaim_bytes": sum(int(row.get("size") or 0) for row in candidates),
        "candidates": candidates,
        "reference_db_errors": [],
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def make_args(plan: Path, **overrides):
    values = {
        "plan": plan,
        "json_report": None,
        "max_count": 30,
        "max_bytes": "512MiB",
        "min_age_hours": 72.0,
        "scope": "global,user",
        "sort": "size-desc",
        "fill_gaps": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class MediaCleanupAllowlistTests(unittest.TestCase):
    def test_allowlist_selects_largest_with_count_and_byte_limits(self):
        allowlist = load_allowlist_module()
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(Path(tmp) / "plan.json", [
                candidate("a", "/data/files/a.mp4", 10),
                candidate("b", "/data/files/b.mp4", 30),
                candidate("c", "/data/files/c.mp4", 20),
            ])

            payload = allowlist.build_allowlist(make_args(plan, max_count=2, max_bytes="40B"))

        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["deletion_enabled"])
        self.assertTrue(payload["review_required"])
        self.assertEqual([row["candidate_id"] for row in payload["allowlist"]], ["b"])
        self.assertEqual(payload["selected_logical_bytes"], 30)
        self.assertEqual(payload["rejected_by_reason"]["max_bytes_reached"], 1)

    def test_allowlist_can_fill_smaller_gaps_when_explicitly_requested(self):
        allowlist = load_allowlist_module()
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(Path(tmp) / "plan.json", [
                candidate("a", "/data/files/a.mp4", 10),
                candidate("b", "/data/files/b.mp4", 30),
                candidate("c", "/data/files/c.mp4", 20),
            ])

            payload = allowlist.build_allowlist(make_args(plan, max_count=2, max_bytes="40B", fill_gaps=True))

        self.assertEqual([row["candidate_id"] for row in payload["allowlist"]], ["b", "a"])
        self.assertEqual(payload["selected_logical_bytes"], 40)

    def test_allowlist_rejects_referenced_recent_and_bad_recheck_candidates(self):
        allowlist = load_allowlist_module()
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(Path(tmp) / "plan.json", [
                candidate("ok", "/data/files/ok.mp4", 10),
                candidate("referenced", "/data/files/ref.mp4", 10, reference_count=1),
                candidate("recent", "/data/files/recent.mp4", 10, age_hours=1),
                candidate("symlink", "/data/files/link.mp4", 10, recheck={"path_exists": True, "regular_file": True, "symlink": True, "allowed_scope": True, "reference_class": "unreferenced"}),
            ])

            payload = allowlist.build_allowlist(make_args(plan))

        self.assertEqual([row["candidate_id"] for row in payload["allowlist"]], ["ok"])
        self.assertEqual(payload["rejected_by_reason"]["referenced"], 1)
        self.assertEqual(payload["rejected_by_reason"]["too_recent"], 1)
        self.assertEqual(payload["rejected_by_reason"]["symlink"], 1)

    def test_allowlist_preflight_rejects_non_dry_run_or_db_error_plan(self):
        allowlist = load_allowlist_module()
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(
                Path(tmp) / "plan.json",
                [candidate("ok", "/data/files/ok.mp4", 10)],
                dry_run=False,
                reference_db_errors=[{"db": "x", "error": "locked"}],
            )

            payload = allowlist.build_allowlist(make_args(plan))

        self.assertIn("plan_must_be_dry_run", payload["preflight_errors"])
        self.assertIn("plan_has_reference_db_errors", payload["preflight_errors"])

    def test_allowlist_json_report_does_not_modify_plan(self):
        allowlist = load_allowlist_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            plan = write_plan(tmp_path / "plan.json", [candidate("ok", "/data/files/ok.mp4", 10)])
            before = plan.read_text(encoding="utf-8")
            out = tmp_path / "allowlist.json"

            payload = allowlist.build_allowlist(make_args(plan, json_report=out))
            allowlist.write_json_report(out, payload)

            self.assertEqual(plan.read_text(encoding="utf-8"), before)
            written = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(written["action"], "media_cleanup_allowlist")

    def test_script_has_no_execute_or_delete_primitives(self):
        source = (ROOT / "deploy" / "media-cleanup-allowlist.py").read_text(encoding="utf-8")

        self.assertNotIn("--execute", source)
        self.assertNotIn(".unlink(", source)
        self.assertNotIn("rmtree(", source)
        self.assertNotIn("os.remove", source)
        self.assertNotIn("DELETE FROM", source)
        self.assertNotIn("UPDATE ", source)


if __name__ == "__main__":
    unittest.main()
