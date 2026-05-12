from __future__ import annotations

import re
from collections import Counter, defaultdict
from urllib.parse import unquote


PERF_LOG_PREFIX = "PERF slow_request"


def _strip_query(path: str) -> str:
    return str(path or "").split("?", 1)[0]


def route_template(path: str) -> str:
    clean = _strip_query(unquote(str(path or "")))
    replacements = [
        (r"/api/game/projects/[^/]+/scenes/[^/]+", "/api/game/projects/{project_id}/scenes/{scene_id}"),
        (r"/api/game/projects/[^/]+/scenes(?:/append)?", lambda m: "/api/game/projects/{project_id}/scenes/append" if m.group(0).endswith("/append") else "/api/game/projects/{project_id}/scenes"),
        (r"/api/game/projects/[^/]+", "/api/game/projects/{project_id}"),
        (r"/api/viral/analyses/[^/]+/plans/rewrite", "/api/viral/analyses/{analysis_id}/plans/rewrite"),
        (r"/api/viral/analyses/[^/]+/plans/save", "/api/viral/analyses/{analysis_id}/plans/save"),
        (r"/api/viral/analyses/[^/]+/plans", "/api/viral/analyses/{analysis_id}/plans"),
        (r"/api/viral/analyses/[^/]+", "/api/viral/analyses/{analysis_id}"),
        (r"/api/files/[^/]+", "/api/files/{file}"),
        (r"/public-files/[^/]+", "/public-files/{file}"),
        (r"/assets/[^/]+", "/assets/{asset}"),
    ]
    for pattern, replacement in replacements:
        match = re.fullmatch(pattern, clean)
        if match:
            return replacement(match) if callable(replacement) else replacement
    return clean or "/"


def performance_category(method: str, path: str) -> str:
    method = str(method or "").upper()
    clean = _strip_query(str(path or ""))
    template = route_template(clean)
    if template in {"/api/game/tasks/status/batch"}:
        return "task_polling"
    if template.startswith(("/api/files/", "/public-files/")) or template == "/api/game/media_info":
        return "media_preview"
    if template in {
        "/api/game/projects",
        "/api/game/projects/{project_id}",
        "/api/game/projects/{project_id}/scenes",
        "/api/game/video_models",
        "/api/game/image_models",
        "/api/game/settings",
        "/api/viral/videos",
        "/api/viral/analyses",
        "/api/viral/analyses/{analysis_id}",
    } and method == "GET":
        return "project_loading"
    if template in {
        "/api/game/analyze_prompt",
        "/api/game/refresh_prompt",
        "/api/game/analyze_video",
        "/api/game/generate_video",
        "/api/game/generate_image",
        "/api/game/replace_video",
        "/api/viral/analyze",
        "/api/viral/analyses/{analysis_id}/plans",
        "/api/viral/analyses/{analysis_id}/plans/rewrite",
    }:
        return "model_request"
    return "other"


def should_log_performance(duration_ms: float, status_code: int, threshold_ms: int) -> bool:
    return duration_ms >= max(0, int(threshold_ms or 0)) or int(status_code or 0) >= 500


def format_perf_log(method: str, path: str, status_code: int, duration_ms: float, threshold_ms: int) -> str:
    template = route_template(path)
    category = performance_category(method, path)
    return (
        f"{PERF_LOG_PREFIX} category={category} method={str(method or '').upper()} "
        f"path={template} status={int(status_code or 0)} duration_ms={duration_ms:.1f} "
        f"threshold_ms={int(threshold_ms or 0)}"
    )


def parse_perf_log_line(line: str) -> dict | None:
    if PERF_LOG_PREFIX not in str(line or ""):
        return None
    pairs = dict(re.findall(r"(\w+)=([^ ]+)", line))
    try:
        duration_ms = float(pairs.get("duration_ms", "0"))
    except ValueError:
        duration_ms = 0.0
    try:
        status = int(float(pairs.get("status", "0")))
    except ValueError:
        status = 0
    return {
        "category": pairs.get("category", "unknown"),
        "method": pairs.get("method", ""),
        "path": pairs.get("path", ""),
        "status": status,
        "duration_ms": duration_ms,
        "threshold_ms": int(float(pairs.get("threshold_ms", "0") or 0)),
        "raw": line.rstrip("\n"),
    }


def parse_access_log_line(line: str) -> dict | None:
    match = re.search(r'INFO:\s+[^ ]+ - "([A-Z]+) ([^ ?"]+)[^"]*" (\d{3})', str(line or ""))
    if not match:
        return None
    method, path, status = match.groups()
    template = route_template(path)
    return {
        "method": method,
        "path": template,
        "category": performance_category(method, path),
        "status": int(status),
    }


def summarize_access_rows(rows: list[dict], top_n: int = 10) -> dict:
    routes = Counter()
    categories = Counter()
    server_errors = Counter()
    for row in rows:
        category = row.get("category") or "unknown"
        key = f"{row.get('method', '')} {row.get('path', '')}".strip()
        routes[key] += 1
        categories[category] += 1
        if int(row.get("status") or 0) >= 500:
            server_errors[key] += 1
    return {
        "sample_count": len(rows),
        "by_category": [
            {"key": key, "count": count}
            for key, count in categories.most_common()
        ],
        "top_routes": [
            {
                "key": key,
                "count": count,
                "server_error_count": server_errors.get(key, 0),
            }
            for key, count in routes.most_common(max(1, top_n))
        ],
    }


def summarize_perf_rows(rows: list[dict], top_n: int = 10) -> dict:
    categories: dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "total_duration_ms": 0.0,
        "max_duration_ms": 0.0,
        "server_error_count": 0,
    })
    routes: dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "total_duration_ms": 0.0,
        "max_duration_ms": 0.0,
        "category": "",
        "server_error_count": 0,
    })
    for row in rows:
        category = row.get("category") or "unknown"
        duration = float(row.get("duration_ms") or 0)
        status = int(row.get("status") or 0)
        cat = categories[category]
        cat["count"] += 1
        cat["total_duration_ms"] += duration
        cat["max_duration_ms"] = max(cat["max_duration_ms"], duration)
        if status >= 500:
            cat["server_error_count"] += 1

        key = f"{row.get('method', '')} {row.get('path', '')}".strip()
        route = routes[key]
        route["count"] += 1
        route["total_duration_ms"] += duration
        route["max_duration_ms"] = max(route["max_duration_ms"], duration)
        route["category"] = category
        if status >= 500:
            route["server_error_count"] += 1

    def finalize(item: tuple[str, dict]) -> dict:
        key, value = item
        count = max(1, int(value["count"]))
        return {
            "key": key,
            "category": value.get("category") or key,
            "count": value["count"],
            "avg_duration_ms": round(value["total_duration_ms"] / count, 1),
            "max_duration_ms": round(value["max_duration_ms"], 1),
            "server_error_count": value["server_error_count"],
        }

    return {
        "sample_count": len(rows),
        "by_category": [
            finalize((key, value))
            for key, value in sorted(categories.items(), key=lambda item: item[1]["max_duration_ms"], reverse=True)
        ],
        "top_routes": [
            finalize(item)
            for item in sorted(routes.items(), key=lambda item: item[1]["max_duration_ms"], reverse=True)[: max(1, top_n)]
        ],
    }
