#!/usr/bin/env python3
"""Read-only performance report for slow request logs.

This script parses PERF slow_request lines emitted by the API service. It does
not call business APIs, does not modify databases, and does not inspect request
bodies or prompts.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


DEFAULT_APP_DIR = Path("/home/deploy/game-video-tool")
DEFAULT_LOG_FILE = DEFAULT_APP_DIR / "app.log"


def load_perf_module():
    path = Path(__file__).resolve().parents[1] / "server" / "performance_observability.py"
    spec = importlib.util.spec_from_file_location("performance_observability_for_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def tail_lines(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text("utf-8", errors="replace").splitlines()
    return lines[-max(1, int(limit or 1)):]


def build_report(args: argparse.Namespace) -> dict:
    perf = load_perf_module()
    rows = [
        row for row in (perf.parse_perf_log_line(line) for line in tail_lines(args.log_file, args.log_tail_lines))
        if row is not None
    ]
    access_rows = [
        row for row in (perf.parse_access_log_line(line) for line in tail_lines(args.log_file, args.log_tail_lines))
        if row is not None
    ]
    summary = perf.summarize_perf_rows(rows, args.top_routes)
    request_volume = perf.summarize_access_rows(access_rows, args.top_routes)
    recommendations: list[str] = []
    if not rows:
        recommendations.append("尚未采集到慢请求样本；需要先部署慢请求日志中间件并等待真实流量。")
    else:
        worst = summary["by_category"][0] if summary["by_category"] else {}
        recommendations.append(
            f"当前最慢类别：{worst.get('key', 'unknown')}，最大耗时 {worst.get('max_duration_ms', 0)}ms。"
        )
        if any(row.get("key") == "model_request" for row in summary["by_category"]):
            recommendations.append("若 model_request 最慢，优先看 provider queue、429/503、上游模型耗时，不要先改项目加载。")
        if any(row.get("key") == "project_loading" for row in summary["by_category"]):
            recommendations.append("若 project_loading 最慢，优先拆项目列表/场景读取和缓存策略。")
        if any(row.get("key") == "media_preview" for row in summary["by_category"]):
            recommendations.append("若 media_preview 最慢，优先查媒体文件大小、预览懒加载和公网传输。")
        if any(row.get("key") == "task_polling" for row in summary["by_category"]):
            recommendations.append("若 task_polling 最慢，优先查 status query 队列、合并缓存和轮询间隔。")

    return {
        "action": "performance_report",
        "readonly": True,
        "mutates_database": False,
        "log_file": str(args.log_file),
        "log_tail_lines": args.log_tail_lines,
        "summary": summary,
        "request_volume": request_volume,
        "recent_samples": rows[-args.recent_samples:],
        "recommendations": recommendations,
    }


def write_json(path: Path | None, payload: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_summary(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("SUMMARY")
    print(f"sample_count: {payload['summary']['sample_count']}")
    print(f"by_category: {payload['summary']['by_category']}")
    print(f"top_routes: {payload['summary']['top_routes']}")
    print(f"request_volume: {payload.get('request_volume', {})}")
    for row in payload["recommendations"]:
        print(f"- {row}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only slow request performance report.")
    parser.add_argument("--app-dir", type=Path, default=DEFAULT_APP_DIR)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG_FILE)
    parser.add_argument("--log-tail-lines", type=int, default=5000)
    parser.add_argument("--top-routes", type=int, default=10)
    parser.add_argument("--recent-samples", type=int, default=20)
    parser.add_argument("--json-report", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.log_file == DEFAULT_LOG_FILE and args.app_dir != DEFAULT_APP_DIR:
        args.log_file = args.app_dir / "app.log"
    payload = build_report(args)
    write_json(args.json_report, payload)
    print_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
