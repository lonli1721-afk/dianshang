"""游戏视频素材工具 — 数据库层"""
from __future__ import annotations

import sqlite3
import json
import uuid
import os
import threading
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from contextvars import ContextVar

DB_PATH = Path(os.environ.get("USER_DATA_DIR", Path.home() / ".game-video-tool")) / "game_video.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_current_db_path: ContextVar[Path] = ContextVar("current_db_path", default=DB_PATH)
_initialized_db_paths: set[Path] = set()
_init_lock = threading.RLock()


def set_db_path(path: Path):
    path = Path(path)
    _current_db_path.set(path)
    init_db(path)


def get_db_path() -> Path:
    return _current_db_path.get()


def get_db(path: Path | None = None):
    conn = sqlite3.connect(str(path or get_db_path()), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: Path | None = None):
    db_path = Path(path or get_db_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _init_lock:
        if db_path in _initialized_db_paths:
            return
        conn = get_db(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS game_projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                user_id TEXT DEFAULT '',
                scenes_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS game_assets (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'character',
                name TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                image_url TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES game_projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS game_tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT DEFAULT '',
                type TEXT NOT NULL DEFAULT 'generate',
                prompt TEXT DEFAULT '',
                character_refs TEXT DEFAULT '[]',
                scene_refs TEXT DEFAULT '[]',
                ref_video_path TEXT DEFAULT '',
                model TEXT DEFAULT '',
                provider TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                video_url TEXT DEFAULT '',
                error TEXT DEFAULT '',
                external_task_id TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS image_tool_tasks (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                provider TEXT DEFAULT '',
                model TEXT DEFAULT '',
                input_payload TEXT DEFAULT '{}',
                result_payload TEXT DEFAULT '{}',
                error TEXT DEFAULT '',
                progress REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_game_projects_updated_at
            ON game_projects(updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_game_assets_project_id
            ON game_assets(project_id);

            CREATE INDEX IF NOT EXISTS idx_game_tasks_project_id_created_at
            ON game_tasks(project_id, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_game_tasks_status_created_at
            ON game_tasks(status, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_game_tasks_external_task_id
            ON game_tasks(external_task_id);

            CREATE INDEX IF NOT EXISTS idx_image_tool_tasks_status_created_at
            ON image_tool_tasks(status, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_image_tool_tasks_created_at
            ON image_tool_tasks(created_at DESC);
        """)
        conn.commit()
        conn.close()
        _run_migrations(db_path)
        _initialized_db_paths.add(db_path)


def _add_column(conn, table: str, col_def: str):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    except sqlite3.OperationalError:
        pass


def _migration_001_create_indexes(conn):
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_game_projects_updated_at
        ON game_projects(updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_game_assets_project_id
        ON game_assets(project_id);

        CREATE INDEX IF NOT EXISTS idx_game_tasks_project_id_created_at
        ON game_tasks(project_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_game_tasks_status_created_at
        ON game_tasks(status, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_game_tasks_external_task_id
        ON game_tasks(external_task_id);
    """)


def _migration_004_create_game_operation_events(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS game_operation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL DEFAULT '',
            operation TEXT NOT NULL,
            provider TEXT DEFAULT '',
            model TEXT DEFAULT '',
            task_id TEXT DEFAULT '',
            status TEXT NOT NULL,
            error TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_game_operation_events_created_at
        ON game_operation_events(created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_game_operation_events_status_created_at
        ON game_operation_events(status, created_at DESC);
    """)


def _migration_005_add_game_task_billing_snapshot(conn):
    _add_column(conn, "game_tasks", "billable_video_seconds REAL DEFAULT 0")
    _add_column(conn, "game_tasks", "estimated_cost_cny REAL DEFAULT 0")
    _add_column(conn, "game_tasks", "billing_status TEXT DEFAULT ''")


def _migration_006_create_viral_workbench(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS viral_videos (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT '',
            source_name TEXT NOT NULL DEFAULT '',
            file_url TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            duration_seconds REAL DEFAULT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS viral_analyses (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT '',
            game_type TEXT DEFAULT '',
            target_user TEXT DEFAULT '',
            platform TEXT DEFAULT '',
            optimization_goal TEXT DEFAULT '',
            model TEXT DEFAULT '',
            status TEXT DEFAULT 'processing',
            video_ids_json TEXT DEFAULT '[]',
            video_urls_json TEXT DEFAULT '[]',
            video_insights_json TEXT DEFAULT '[]',
            tags_json TEXT DEFAULT '[]',
            plans_json TEXT DEFAULT '[]',
            error TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_viral_videos_user_created_at
        ON viral_videos(user_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_viral_analyses_user_updated_at
        ON viral_analyses(user_id, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_viral_analyses_status_updated_at
        ON viral_analyses(status, updated_at DESC);
    """)


def _migration_007_add_viral_video_insights(conn):
    _add_column(conn, "viral_analyses", "video_insights_json TEXT DEFAULT '[]'")


def _migration_008_create_image_tool_tasks(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS image_tool_tasks (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            provider TEXT DEFAULT '',
            model TEXT DEFAULT '',
            input_payload TEXT DEFAULT '{}',
            result_payload TEXT DEFAULT '{}',
            error TEXT DEFAULT '',
            progress REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_image_tool_tasks_status_created_at
        ON image_tool_tasks(status, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_image_tool_tasks_created_at
        ON image_tool_tasks(created_at DESC);
    """)


_MIGRATIONS: list[tuple[int, str, callable]] = [
    (1, "create game project/task indexes", _migration_001_create_indexes),
    (4, "create game operation events table", _migration_004_create_game_operation_events),
    (5, "add game task billing snapshot columns", _migration_005_add_game_task_billing_snapshot),
    (6, "create viral workbench tables", _migration_006_create_viral_workbench),
    (7, "add viral video insights", _migration_007_add_viral_video_insights),
    (8, "create image tool tasks", _migration_008_create_image_tool_tasks),
]


def _run_migrations(path: Path | None = None):
    conn = get_db(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT DEFAULT '',
            applied_at TEXT NOT NULL
        )
    """)
    conn.commit()
    applied = {r[0] for r in conn.execute("SELECT version FROM _schema_version").fetchall()}
    for version, description, migrate_fn in _MIGRATIONS:
        if version in applied:
            continue
        migrate_fn(conn)
        conn.execute(
            "INSERT INTO _schema_version (version, description, applied_at) VALUES (?, ?, ?)",
            (version, description, datetime.utcnow().isoformat() + "Z"),
        )
        conn.commit()
    conn.close()


def _now():
    return datetime.utcnow().isoformat() + "Z"


def _uid():
    return uuid.uuid4().hex[:12]


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def _loads_json(value, default):
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, type(default)) else default
    except Exception:
        return default


# ──────────────────── Game Projects ────────────────────

def create_game_project(name: str, description: str = "", user_id: str = "") -> dict:
    conn = get_db()
    pid = _uid()
    now = _now()
    conn.execute(
        "INSERT INTO game_projects (id, name, description, user_id, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, name, description, user_id, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM game_projects WHERE id=?", (pid,)).fetchone()
    conn.close()
    return row_to_dict(row)


def list_game_projects(user_id: str = "", limit: int = 50) -> list:
    conn = get_db()
    q = """
        SELECT id, name, description, user_id, created_at, updated_at
        FROM game_projects
        WHERE 1=1
    """
    params: list = []
    if user_id:
        q += " AND user_id=?"
        params.append(user_id)
    q += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


def get_game_project(project_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM game_projects WHERE id=?", (project_id,)).fetchone()
    conn.close()
    return row_to_dict(row)


def update_game_project(project_id: str, **kwargs):
    conn = get_db()
    kwargs["updated_at"] = _now()
    sets = ", ".join(f'"{k}"=?' for k in kwargs)
    vals = list(kwargs.values()) + [project_id]
    conn.execute(f"UPDATE game_projects SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


def _normalize_project_scenes(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value or "{}")
        except Exception:
            value = {}
    if isinstance(value, list):
        return {"generate": value, "replace": [], "tabState": None}
    if not isinstance(value, dict):
        return {"generate": [], "replace": [], "tabState": None}
    return {
        "generate": value.get("generate") if isinstance(value.get("generate"), list) else [],
        "replace": value.get("replace") if isinstance(value.get("replace"), list) else [],
        "tabState": value.get("tabState"),
    }


def append_game_project_scenes(project_id: str, scenes: list[dict]) -> dict | None:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT scenes_json FROM game_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            conn.rollback()
            return None
        data = _normalize_project_scenes(row["scenes_json"])
        current = data["generate"]
        appended: list[dict] = []
        next_index = len(current) + 1
        for item in scenes or []:
            if not isinstance(item, dict):
                continue
            scene = dict(item)
            scene["idx"] = next_index
            next_index += 1
            current.append(scene)
            appended.append(scene)
        now = _now()
        conn.execute(
            "UPDATE game_projects SET scenes_json=?, updated_at=? WHERE id=?",
            (json.dumps(data, ensure_ascii=False), now, project_id),
        )
        conn.commit()
        return {"scenes": data, "appended": appended}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def patch_game_project_scene(project_id: str, scene_id: str, patch: dict) -> dict | None:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT scenes_json FROM game_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            conn.rollback()
            return None
        data = _normalize_project_scenes(row["scenes_json"])
        updated_scene = None
        for group in ("generate", "replace"):
            next_items = []
            changed = False
            for scene in data[group]:
                if isinstance(scene, dict) and scene.get("id") == scene_id:
                    updated_scene = {**scene, **(patch or {}), "id": scene_id}
                    next_items.append(updated_scene)
                    changed = True
                else:
                    next_items.append(scene)
            if changed:
                data[group] = next_items
                break
        if not updated_scene:
            conn.rollback()
            return {"scenes": data, "scene": None}
        now = _now()
        conn.execute(
            "UPDATE game_projects SET scenes_json=?, updated_at=? WHERE id=?",
            (json.dumps(data, ensure_ascii=False), now, project_id),
        )
        conn.commit()
        return {"scenes": data, "scene": updated_scene}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_game_project(project_id: str):
    conn = get_db()
    conn.execute("DELETE FROM game_projects WHERE id=?", (project_id,))
    conn.commit()
    conn.close()


# ──────────────────── Game Assets ────────────────────

def create_game_asset(project_id: str, type_: str, name: str, description: str = "", image_url: str = "") -> dict:
    conn = get_db()
    aid = _uid()
    now = _now()
    conn.execute(
        "INSERT INTO game_assets (id, project_id, type, name, description, image_url, created_at) VALUES (?,?,?,?,?,?,?)",
        (aid, project_id, type_, name, description, image_url, now),
    )
    conn.execute("UPDATE game_projects SET updated_at=? WHERE id=?", (now, project_id))
    conn.commit()
    row = conn.execute("SELECT * FROM game_assets WHERE id=?", (aid,)).fetchone()
    conn.close()
    return row_to_dict(row)


def list_game_assets(project_id: str, type_: str = "") -> list:
    conn = get_db()
    q = "SELECT * FROM game_assets WHERE project_id=?"
    params: list = [project_id]
    if type_:
        q += " AND type=?"
        params.append(type_)
    q += " ORDER BY created_at"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


def get_game_asset(asset_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM game_assets WHERE id=?", (asset_id,)).fetchone()
    conn.close()
    return row_to_dict(row)


def update_game_asset(asset_id: str, **kwargs):
    conn = get_db()
    sets = ", ".join(f'"{k}"=?' for k in kwargs)
    vals = list(kwargs.values()) + [asset_id]
    conn.execute(f"UPDATE game_assets SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


def delete_game_asset(asset_id: str):
    conn = get_db()
    conn.execute("DELETE FROM game_assets WHERE id=?", (asset_id,))
    conn.commit()
    conn.close()


# ──────────────────── Game Tasks ────────────────────

def _parse_game_task(row) -> dict | None:
    if row is None:
        return None
    d = row_to_dict(row)
    for k in ("character_refs", "scene_refs"):
        d[k] = json.loads(d.get(k, "[]"))
    return d


def create_game_task(project_id: str, type_: str, prompt: str = "", model: str = "",
                     provider: str = "", character_refs: list | None = None,
                     scene_refs: list | None = None, ref_video_path: str = "",
                     external_task_id: str = "") -> dict:
    conn = get_db()
    tid = _uid()
    now = _now()
    cr_json = json.dumps(character_refs or [], ensure_ascii=False)
    sr_json = json.dumps(scene_refs or [], ensure_ascii=False)
    conn.execute(
        "INSERT INTO game_tasks (id, project_id, type, prompt, character_refs, scene_refs, "
        "ref_video_path, model, provider, status, external_task_id, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (tid, project_id, type_, prompt, cr_json, sr_json, ref_video_path,
         model, provider, "processing", external_task_id, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM game_tasks WHERE id=?", (tid,)).fetchone()
    conn.close()
    return _parse_game_task(row)


def list_game_tasks(project_id: str = "", status: str = "", limit: int = 50) -> list:
    conn = get_db()
    q = "SELECT * FROM game_tasks WHERE 1=1"
    params: list = []
    if project_id:
        q += " AND project_id=?"
        params.append(project_id)
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_parse_game_task(r) for r in rows]


def get_game_task(task_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM game_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return _parse_game_task(row)


def get_game_task_by_external_id(ext_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM game_tasks WHERE external_task_id=?", (ext_id,)).fetchone()
    conn.close()
    return _parse_game_task(row)


def update_game_task(task_id: str, **kwargs):
    conn = get_db()
    for k in ("character_refs", "scene_refs"):
        if k in kwargs and isinstance(kwargs[k], list):
            kwargs[k] = json.dumps(kwargs[k], ensure_ascii=False)
    kwargs["updated_at"] = _now()
    sets = ", ".join(f'"{k}"=?' for k in kwargs)
    vals = list(kwargs.values()) + [task_id]
    conn.execute(f"UPDATE game_tasks SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


def delete_game_task(task_id: str):
    conn = get_db()
    conn.execute("DELETE FROM game_tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()


# ──────────────────── Image Tool Tasks ────────────────────

def _parse_image_tool_task(row) -> dict | None:
    if row is None:
        return None
    d = row_to_dict(row)
    d["input_payload"] = _loads_json(d.get("input_payload"), {})
    d["result_payload"] = _loads_json(d.get("result_payload"), {})
    return d


def create_image_tool_task(
    *,
    type_: str,
    provider: str = "",
    model: str = "",
    input_payload: dict | None = None,
) -> dict:
    conn = get_db()
    tid = f"imgtask_{_uid()}"
    now = _now()
    conn.execute(
        "INSERT INTO image_tool_tasks "
        "(id, type, status, provider, model, input_payload, result_payload, error, progress, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tid,
            type_,
            "queued",
            provider,
            model,
            json.dumps(input_payload or {}, ensure_ascii=False),
            "{}",
            "",
            0,
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM image_tool_tasks WHERE id=?", (tid,)).fetchone()
    conn.close()
    return _parse_image_tool_task(row)


def get_image_tool_task(task_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM image_tool_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return _parse_image_tool_task(row)


def list_image_tool_tasks(status: str = "", limit: int = 50) -> list[dict]:
    conn = get_db()
    q = "SELECT * FROM image_tool_tasks WHERE 1=1"
    params: list = []
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_parse_image_tool_task(row) for row in rows]


def update_image_tool_task(task_id: str, **kwargs):
    if not kwargs:
        return
    conn = get_db()
    for key in ("input_payload", "result_payload"):
        if key in kwargs and not isinstance(kwargs[key], str):
            kwargs[key] = json.dumps(kwargs[key] or {}, ensure_ascii=False)
    if "error" in kwargs and kwargs["error"] is not None:
        kwargs["error"] = str(kwargs["error"])[:2000]
    kwargs["updated_at"] = _now()
    sets = ", ".join(f'"{key}"=?' for key in kwargs)
    vals = list(kwargs.values()) + [task_id]
    conn.execute(f"UPDATE image_tool_tasks SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


def delete_image_tool_task(task_id: str) -> bool:
    conn = get_db()
    cursor = conn.execute("DELETE FROM image_tool_tasks WHERE id=?", (task_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def mark_stale_image_tool_tasks_interrupted() -> int:
    conn = get_db()
    now = _now()
    cursor = conn.execute(
        "UPDATE image_tool_tasks "
        "SET status='failed', error='服务重启或任务运行中断，请重新提交。', updated_at=? "
        "WHERE status IN ('queued', 'running')",
        (now,),
    )
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def create_game_operation_event(
    *,
    project_id: str = "",
    operation: str,
    provider: str = "",
    model: str = "",
    status: str = "failed",
    task_id: str = "",
    error: str = "",
) -> dict:
    """Append one row to game_operation_events. Best-effort observability —
    callers wrap this in try/except so a write failure here must not
    cascade into the user-visible operation result."""
    conn = get_db()
    now = _now()
    safe_error = (error or "")[:2000]
    cursor = conn.execute(
        """
        INSERT INTO game_operation_events
            (project_id, operation, provider, model, task_id, status, error, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (project_id, operation, provider, model, task_id, status, safe_error, now),
    )
    rowid = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": rowid,
        "project_id": project_id,
        "operation": operation,
        "status": status,
        "created_at": now,
    }


# ──────────────────── Viral Workbench ────────────────────

def _parse_viral_video(row) -> dict | None:
    return row_to_dict(row)


def _parse_viral_analysis(row) -> dict | None:
    if row is None:
        return None
    d = row_to_dict(row)
    d["video_ids"] = _loads_json(d.pop("video_ids_json", "[]"), [])
    d["video_urls"] = _loads_json(d.pop("video_urls_json", "[]"), [])
    d["video_insights"] = _loads_json(d.pop("video_insights_json", "[]"), [])
    d["tags"] = _loads_json(d.pop("tags_json", "[]"), [])
    d["plans"] = _loads_json(d.pop("plans_json", "[]"), [])
    return d


def create_viral_video(
    *,
    user_id: str = "",
    source_name: str,
    file_url: str,
    file_size: int = 0,
    duration_seconds: float | None = None,
) -> dict:
    conn = get_db()
    vid = _uid()
    now = _now()
    conn.execute(
        """
        INSERT INTO viral_videos
            (id, user_id, source_name, file_url, file_size, duration_seconds, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (vid, user_id, source_name, file_url, int(file_size or 0), duration_seconds, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM viral_videos WHERE id=?", (vid,)).fetchone()
    conn.close()
    return _parse_viral_video(row)


def list_viral_videos(user_id: str = "", limit: int = 100) -> list:
    conn = get_db()
    q = "SELECT * FROM viral_videos WHERE 1=1"
    params: list = []
    if user_id:
        q += " AND user_id=?"
        params.append(user_id)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_parse_viral_video(r) for r in rows]


def get_viral_video(video_id: str, user_id: str = "") -> dict | None:
    conn = get_db()
    q = "SELECT * FROM viral_videos WHERE id=?"
    params: list = [video_id]
    if user_id:
        q += " AND user_id=?"
        params.append(user_id)
    row = conn.execute(q, params).fetchone()
    conn.close()
    return _parse_viral_video(row)


def get_viral_videos_by_ids(video_ids: list[str], user_id: str = "") -> list:
    ids = [v for v in (video_ids or []) if v]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    conn = get_db()
    q = f"SELECT * FROM viral_videos WHERE id IN ({placeholders})"
    params: list = list(ids)
    if user_id:
        q += " AND user_id=?"
        params.append(user_id)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    by_id = {r["id"]: _parse_viral_video(r) for r in rows}
    return [by_id[v] for v in ids if v in by_id]


def delete_viral_video(video_id: str, user_id: str = "") -> None:
    conn = get_db()
    if user_id:
        conn.execute("DELETE FROM viral_videos WHERE id=? AND user_id=?", (video_id, user_id))
    else:
        conn.execute("DELETE FROM viral_videos WHERE id=?", (video_id,))
    conn.commit()
    conn.close()


def create_viral_analysis(
    *,
    user_id: str = "",
    game_type: str = "",
    target_user: str = "",
    platform: str = "",
    optimization_goal: str = "",
    model: str = "",
    video_ids: list[str] | None = None,
    video_urls: list[str] | None = None,
    video_insights: list | None = None,
    tags: list | None = None,
    plans: list | None = None,
    status: str = "processing",
    error: str = "",
) -> dict:
    conn = get_db()
    aid = _uid()
    now = _now()
    conn.execute(
        """
        INSERT INTO viral_analyses
            (id, user_id, game_type, target_user, platform, optimization_goal, model,
             status, video_ids_json, video_urls_json, video_insights_json, tags_json, plans_json, error,
             created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            aid,
            user_id,
            game_type,
            target_user,
            platform,
            optimization_goal,
            model,
            status,
            json.dumps(video_ids or [], ensure_ascii=False),
            json.dumps(video_urls or [], ensure_ascii=False),
            json.dumps(video_insights or [], ensure_ascii=False),
            json.dumps(tags or [], ensure_ascii=False),
            json.dumps(plans or [], ensure_ascii=False),
            (error or "")[:2000],
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM viral_analyses WHERE id=?", (aid,)).fetchone()
    conn.close()
    return _parse_viral_analysis(row)


def list_viral_analyses(user_id: str = "", limit: int = 50) -> list:
    conn = get_db()
    q = "SELECT * FROM viral_analyses WHERE 1=1"
    params: list = []
    if user_id:
        q += " AND user_id=?"
        params.append(user_id)
    q += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_parse_viral_analysis(r) for r in rows]


def get_viral_analysis(analysis_id: str, user_id: str = "") -> dict | None:
    conn = get_db()
    q = "SELECT * FROM viral_analyses WHERE id=?"
    params: list = [analysis_id]
    if user_id:
        q += " AND user_id=?"
        params.append(user_id)
    row = conn.execute(q, params).fetchone()
    conn.close()
    return _parse_viral_analysis(row)


def delete_viral_analysis(analysis_id: str, user_id: str = "") -> None:
    conn = get_db()
    if user_id:
        conn.execute("DELETE FROM viral_analyses WHERE id=? AND user_id=?", (analysis_id, user_id))
    else:
        conn.execute("DELETE FROM viral_analyses WHERE id=?", (analysis_id,))
    conn.commit()
    conn.close()


def is_viral_file_referenced(file_url: str, user_id: str = "") -> bool:
    if not file_url:
        return False
    conn = get_db()
    try:
        params: list = [file_url]
        q = "SELECT 1 FROM viral_videos WHERE file_url=?"
        if user_id:
            q += " AND user_id=?"
            params.append(user_id)
        q += " LIMIT 1"
        if conn.execute(q, params).fetchone():
            return True

        needle = f"%{file_url}%"
        params = [needle]
        q = "SELECT 1 FROM viral_analyses WHERE video_urls_json LIKE ?"
        if user_id:
            q += " AND user_id=?"
            params.append(user_id)
        q += " LIMIT 1"
        return bool(conn.execute(q, params).fetchone())
    finally:
        conn.close()


def update_viral_analysis(analysis_id: str, **kwargs):
    if not kwargs:
        return
    json_fields = {
        "video_ids": "video_ids_json",
        "video_urls": "video_urls_json",
        "video_insights": "video_insights_json",
        "tags": "tags_json",
        "plans": "plans_json",
    }
    for public_key, column_key in json_fields.items():
        if public_key in kwargs:
            kwargs[column_key] = json.dumps(kwargs.pop(public_key) or [], ensure_ascii=False)
    if "error" in kwargs:
        kwargs["error"] = (kwargs.get("error") or "")[:2000]
    conn = get_db()
    kwargs["updated_at"] = _now()
    sets = ", ".join(f'"{k}"=?' for k in kwargs)
    vals = list(kwargs.values()) + [analysis_id]
    conn.execute(f"UPDATE viral_analyses SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


def append_viral_analysis_plans(
    analysis_id: str,
    plans: list[dict],
    user_id: str = "",
    status: str = "completed",
    error: str = "",
) -> dict | None:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        q = "SELECT * FROM viral_analyses WHERE id=?"
        params: list = [analysis_id]
        if user_id:
            q += " AND user_id=?"
            params.append(user_id)
        row = conn.execute(q, params).fetchone()
        if not row:
            conn.rollback()
            return None
        existing = _loads_json(row["plans_json"], [])
        existing_ids = {str(plan.get("id")) for plan in existing if isinstance(plan, dict) and plan.get("id")}
        incoming: list[dict] = []
        for item in plans or []:
            if not isinstance(item, dict):
                continue
            plan = dict(item)
            base_id = str(plan.get("id") or f"plan-{_uid()[:8]}")
            plan_id = base_id
            while plan_id in existing_ids:
                plan_id = f"{base_id}-{_uid()[:6]}"
            plan["id"] = plan_id
            existing_ids.add(plan_id)
            incoming.append(plan)
        if not incoming:
            conn.rollback()
            return _parse_viral_analysis(row)
        now = _now()
        conn.execute(
            """
            UPDATE viral_analyses
            SET plans_json=?, status=?, error=?, updated_at=?
            WHERE id=?
            """,
            (
                json.dumps(incoming + existing, ensure_ascii=False),
                status,
                (error or "")[:2000],
                now,
                analysis_id,
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM viral_analyses WHERE id=?", (analysis_id,)).fetchone()
        return _parse_viral_analysis(updated)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_viral_analysis_plan(
    analysis_id: str,
    plan: dict,
    user_id: str = "",
    status: str = "completed",
) -> dict | None:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        q = "SELECT * FROM viral_analyses WHERE id=?"
        params: list = [analysis_id]
        if user_id:
            q += " AND user_id=?"
            params.append(user_id)
        row = conn.execute(q, params).fetchone()
        if not row:
            conn.rollback()
            return None
        incoming = dict(plan or {})
        incoming_id = str(incoming.get("id") or f"manual-{_uid()[:8]}")
        incoming["id"] = incoming_id
        existing = _loads_json(row["plans_json"], [])
        updated = False
        next_plans: list[dict] = []
        for item in existing:
            if isinstance(item, dict) and item.get("id") == incoming_id:
                next_plans.append(incoming)
                updated = True
            else:
                next_plans.append(item)
        if not updated:
            next_plans.append(incoming)
        now = _now()
        conn.execute(
            """
            UPDATE viral_analyses
            SET plans_json=?, status=?, updated_at=?
            WHERE id=?
            """,
            (json.dumps(next_plans, ensure_ascii=False), status, now, analysis_id),
        )
        conn.commit()
        updated_row = conn.execute("SELECT * FROM viral_analyses WHERE id=?", (analysis_id,)).fetchone()
        return _parse_viral_analysis(updated_row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_project_file_reference_values(project_id: str) -> list[str]:
    conn = get_db()
    values: list[str] = []

    row = conn.execute(
        "SELECT scenes_json FROM game_projects WHERE id=?",
        (project_id,),
    ).fetchone()
    if row and row["scenes_json"]:
        values.append(row["scenes_json"])

    asset_rows = conn.execute(
        "SELECT image_url FROM game_assets WHERE project_id=?",
        (project_id,),
    ).fetchall()
    values.extend(r["image_url"] for r in asset_rows if r["image_url"])

    task_rows = conn.execute(
        """
        SELECT character_refs, scene_refs, ref_video_path, video_url
        FROM game_tasks
        WHERE project_id=?
        """,
        (project_id,),
    ).fetchall()
    for row in task_rows:
        for key in ("character_refs", "scene_refs", "ref_video_path", "video_url"):
            if row[key]:
                values.append(row[key])

    conn.close()
    return values


def _filename_from_file_reference(value: str) -> str:
    if not isinstance(value, str) or "/api/files/" not in value:
        return ""
    filename = value.split("/api/files/", 1)[1].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
        return ""
    return filename


def _collect_file_reference_filenames(value) -> set[str]:
    filenames: set[str] = set()
    if isinstance(value, str):
        filename = _filename_from_file_reference(value)
        if filename:
            filenames.add(filename)
    elif isinstance(value, dict):
        for item in value.values():
            filenames.update(_collect_file_reference_filenames(item))
    elif isinstance(value, list):
        for item in value:
            filenames.update(_collect_file_reference_filenames(item))
    return filenames


def _reference_value_has_filename(value, filename: str) -> bool:
    if not filename:
        return False
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value or "")
        except Exception:
            parsed = value
    return filename in _collect_file_reference_filenames(parsed)


def is_file_referenced_elsewhere(filename: str, exclude_project_id: str = "") -> bool:
    if not filename:
        return False

    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT scenes_json
            FROM game_projects
            WHERE id != ? AND scenes_json != ''
            """,
            (exclude_project_id or "",),
        ).fetchall()
        if any(_reference_value_has_filename(row["scenes_json"], filename) for row in rows):
            return True

        rows = conn.execute(
            """
            SELECT image_url
            FROM game_assets
            WHERE project_id != ? AND image_url != ''
            """,
            (exclude_project_id or "",),
        ).fetchall()
        if any(_reference_value_has_filename(row["image_url"], filename) for row in rows):
            return True

        rows = conn.execute(
            """
            SELECT character_refs, scene_refs, ref_video_path, video_url
            FROM game_tasks
            WHERE project_id != ?
            """,
            (exclude_project_id or "",),
        ).fetchall()
        for row in rows:
            if any(_reference_value_has_filename(row[key], filename) for key in ("character_refs", "scene_refs", "ref_video_path", "video_url")):
                return True
        return False
    finally:
        conn.close()


def is_file_referenced_in_project_state(filename: str, project_id: str = "") -> bool:
    if not filename or not project_id:
        return False

    conn = get_db()
    try:
        row = conn.execute(
            """
            SELECT scenes_json
            FROM game_projects
            WHERE id=?
            """,
            (project_id,),
        ).fetchone()
        if row and _reference_value_has_filename(row["scenes_json"], filename):
            return True

        rows = conn.execute(
            """
            SELECT image_url
            FROM game_assets
            WHERE project_id=? AND image_url != ''
            """,
            (project_id,),
        ).fetchall()
        return any(_reference_value_has_filename(row["image_url"], filename) for row in rows)
    finally:
        conn.close()


# ──────────────────── User Settings ────────────────────

def get_user_setting(key: str, default: str = "") -> str:
    conn = get_db()
    row = conn.execute("SELECT value FROM user_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_user_setting(key: str, value: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO user_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_all_user_settings(prefix: str = "") -> dict:
    conn = get_db()
    if prefix:
        rows = conn.execute("SELECT key, value FROM user_settings WHERE key LIKE ?", (prefix + "%",)).fetchall()
    else:
        rows = conn.execute("SELECT key, value FROM user_settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


init_db()
