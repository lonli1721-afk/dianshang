"""Cloud Sync Manager — background sync of generated media + SQLite DBs to the cloud, with local auto-backup."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import auth

logger = logging.getLogger("wanpi.cloud_sync")


async def _post_file_multipart(url: str, filepath: Path, token: str, client=None, timeout: int = 120, upload_name: str = ""):
    import httpx

    headers = {"Authorization": f"Bearer {token}"}
    with filepath.open("rb") as f:
        files = {"file": (upload_name or filepath.name, f, "application/octet-stream")}
        if client is None:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as tmp:
                return await tmp.post(url, files=files, headers=headers)
        return await client.post(url, files=files, headers=headers, timeout=timeout)


def _collect_all_database_paths() -> list[Path]:
    """Auth DB + every per-user game database under USER_DATA_DIR/users/*/database.db"""
    paths: list[Path] = []
    auth_db = auth.AUTH_DB_PATH
    if auth_db.exists():
        paths.append(auth_db)
    users_root = auth.USER_DATA_DIR / "users"
    if users_root.is_dir():
        for uid_dir in sorted(users_root.iterdir()):
            if not uid_dir.is_dir():
                continue
            dbp = uid_dir / "database.db"
            if dbp.is_file():
                paths.append(dbp)
    return paths


def _sqlite_backup(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(dst))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


class CloudSyncManager:
    """Background manager: upload generated files + DB snapshots to cloud; local DB backup on disk."""

    def __init__(self, settings_manager, db_module):
        self._settings = settings_manager
        self._db = db_module
        self._file_queue: asyncio.Queue = asyncio.Queue()
        self._db_dirty = False
        self._dirty_db_paths: set[Path] = set()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_quick_db_sync = 0.0
        self._last_cloud_full_sync = 0.0
        self._last_local_backup = 0.0
        # counts are for observability, not business data
        self._synced_file_count = 0
        self._synced_db_count = 0
        self._error_count = 0
        self._last_error = ""
        self._local_backup_interval = 300
        self._local_backup_keep = 14
        self._last_local_backup_iso = ""
        # realtime observability
        self._wake = asyncio.Event()
        self._last_success_at = ""
        self._last_success_kind = ""
        self._last_uploaded_file = ""
        self._last_uploaded_file_at = ""
        self._last_pushed_db = ""
        self._last_pushed_db_at = ""
        self._last_error_at = ""
        self._last_error_item = ""

    @property
    def _cloud_url(self) -> str:
        return (self._settings.get("cloud_url", "") or "").rstrip("/")

    @property
    def _cloud_token(self) -> str:
        return self._settings.get("cloud_token", "") or ""

    @property
    def _is_self_cloud(self) -> bool:
        cloud_url = self._cloud_url
        public_base = (os.environ.get("PUBLIC_BASE_URL", "") or "").rstrip("/")
        if not cloud_url or not public_base:
            return False
        try:
            cloud = urlparse(cloud_url)
            public = urlparse(public_base)
        except Exception:
            return cloud_url == public_base
        cloud_host = (cloud.hostname or "").lower()
        public_host = (public.hostname or "").lower()
        if not cloud_host or cloud_host != public_host:
            return False
        cloud_port = cloud.port
        public_port = public.port
        return cloud_port is None or public_port is None or cloud_port == public_port

    @property
    def _enabled(self) -> bool:
        return bool(self._cloud_url and self._cloud_token
                     and not self._is_self_cloud
                     and self._settings.get("auto_sync_enabled", False))

    @property
    def _interval(self) -> int:
        """Seconds between full cloud DB pushes (from settings: minutes)."""
        v = self._settings.get("auto_sync_interval", 3)
        return max(60, int(v) * 60)

    def queue_file(self, filepath: Path):
        filepath = Path(filepath)
        if self._enabled and filepath.is_file():
            try:
                self._file_queue.put_nowait(filepath)
            except Exception:
                pass
            self._wake.set()

    def mark_db_dirty(self):
        self._db_dirty = True
        try:
            self._dirty_db_paths.add(self._db.get_db_path())
        except Exception:
            pass
        try:
            if auth.AUTH_DB_PATH.exists():
                self._dirty_db_paths.add(auth.AUTH_DB_PATH)
        except Exception:
            pass
        self._wake.set()

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "connected": bool(self._cloud_url and self._cloud_token),
            "cloud_url": self._cloud_url,
            "queue_size": self._file_queue.qsize(),
            "synced_file_count": self._synced_file_count,
            "synced_db_count": self._synced_db_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
            "last_success_at": self._last_success_at,
            "last_success_kind": self._last_success_kind,
            "last_uploaded_file": self._last_uploaded_file,
            "last_uploaded_file_at": self._last_uploaded_file_at,
            "last_pushed_db": self._last_pushed_db,
            "last_pushed_db_at": self._last_pushed_db_at,
            "last_error_at": self._last_error_at,
            "last_error_item": self._last_error_item,
            "local_backup_interval_sec": self._local_backup_interval,
            "last_local_backup_at": self._last_local_backup_iso,
        }

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while self._running:
            try:
                now = time.time()
                if now - self._last_local_backup >= self._local_backup_interval:
                    self._local_backup_dbs()
                    self._last_local_backup = now

                if self._enabled:
                    await self._process_file_queue()
                    if self._db_dirty and (now - self._last_quick_db_sync) >= 45:
                        await self._sync_dirty_dbs()
                        self._last_quick_db_sync = now
                        self._db_dirty = False
                    if (now - self._last_cloud_full_sync) >= self._interval:
                        await self._push_all_databases_cloud()
                        self._last_cloud_full_sync = now
            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)[:200]
                self._last_error_at = datetime.now().replace(microsecond=0).isoformat()
                self._last_error_item = "loop"
                logger.exception("cloud_sync loop: %s", e)
            # realtime wake: if new work arrives, queue_file/mark_db_dirty will set _wake
            self._wake.clear()
            timeout = 0.35 if (self._enabled and not self._file_queue.empty()) else 2.0
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass

    async def _process_file_queue(self):
        import deps as _deps
        batch_count = 0
        while not self._file_queue.empty() and batch_count < 30:
            try:
                filepath = self._file_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if not filepath.exists():
                continue
            batch_count += 1
            try:
                resp = await _post_file_multipart(
                    f"{self._cloud_url}/api/sync/push-file",
                    filepath,
                    self._cloud_token,
                    client=_deps.http_client,
                    timeout=120,
                )
                if resp.status_code == 200:
                    self._synced_file_count += 1
                    now_iso = datetime.now().replace(microsecond=0).isoformat()
                    self._last_success_at = now_iso
                    self._last_success_kind = "file"
                    self._last_uploaded_file = filepath.name
                    self._last_uploaded_file_at = now_iso
                else:
                    self._error_count += 1
                    self._last_error = f"push-file {filepath.name}: HTTP {resp.status_code}"
                    self._last_error_at = datetime.now().replace(microsecond=0).isoformat()
                    self._last_error_item = filepath.name
            except Exception as e:
                self._error_count += 1
                self._last_error = f"push-file {filepath.name}: {str(e)[:100]}"
                self._last_error_at = datetime.now().replace(microsecond=0).isoformat()
                self._last_error_item = filepath.name
                try:
                    self._file_queue.put_nowait(filepath)
                except Exception:
                    pass
                break

    async def _sync_dirty_dbs(self):
        paths = list(self._dirty_db_paths)
        self._dirty_db_paths.clear()
        if not paths:
            paths = [self._db.get_db_path()]
        for db_path in paths:
            if db_path and Path(db_path).exists():
                await self._sync_db_cloud(db_path)

    async def _push_all_databases_cloud(self):
        for db_path in _collect_all_database_paths():
            await self._sync_db_cloud(db_path)

    async def _sync_db_cloud(self, db_path: Path | None = None):
        import deps as _deps
        db_path = Path(db_path) if db_path else self._db.get_db_path()
        if not db_path.exists():
            return
        staged_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="game-video-db-sync-", suffix=f"-{db_path.name}", delete=False) as tmp:
                staged_path = Path(tmp.name)
            _sqlite_backup(db_path, staged_path)
            resp = await _post_file_multipart(
                f"{self._cloud_url}/api/sync/push-db",
                staged_path,
                self._cloud_token,
                client=_deps.http_client,
                timeout=120,
                upload_name=db_path.name,
            )
            if resp.status_code == 200:
                self._synced_db_count += 1
                now_iso = datetime.now().replace(microsecond=0).isoformat()
                self._last_success_at = now_iso
                self._last_success_kind = "db"
                self._last_pushed_db = db_path.name
                self._last_pushed_db_at = now_iso
            else:
                self._error_count += 1
                self._last_error = f"push-db {db_path.name}: HTTP {resp.status_code}"
                self._last_error_at = datetime.now().replace(microsecond=0).isoformat()
                self._last_error_item = db_path.name
        except Exception as e:
            self._error_count += 1
            self._last_error = f"push-db {db_path.name}: {str(e)[:100]}"
            self._last_error_at = datetime.now().replace(microsecond=0).isoformat()
            self._last_error_item = db_path.name
        finally:
            if staged_path:
                try:
                    staged_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _local_backup_dbs(self):
        """Write timestamped SQLite backups under USER_DATA_DIR/backups/auto/."""
        try:
            root = auth.USER_DATA_DIR / "backups" / "auto"
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            batch = root / ts
            paths = _collect_all_database_paths()
            if not paths:
                legacy = self._db.get_db_path()
                if legacy.exists():
                    paths = [legacy]
            for src in paths:
                try:
                    rel = src.relative_to(auth.USER_DATA_DIR)
                    dest = batch / str(rel).replace("\\", "/")
                except ValueError:
                    dest = batch / src.name
                try:
                    _sqlite_backup(src, dest)
                except Exception as e:
                    logger.warning("local backup failed for %s: %s", src, e)
            self._rotate_local_backups(root)
            self._last_local_backup_iso = datetime.now().replace(microsecond=0).isoformat()
        except Exception as e:
            logger.warning("local backup batch failed: %s", e)

    def _rotate_local_backups(self, root: Path):
        try:
            dirs = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name)
            while len(dirs) > self._local_backup_keep:
                old = dirs.pop(0)
                try:
                    shutil.rmtree(old, ignore_errors=True)
                except Exception:
                    pass
        except Exception:
            pass

    async def force_sync_now(self):
        if not self._enabled:
            return {"error": "云端同步未启用"}
        await self._process_file_queue()
        # do not fabricate "uploads" when nothing changed:
        # - always push dirty dbs if any
        # - if no dirty flag, do not push all dbs
        if self._db_dirty or self._dirty_db_paths:
            await self._sync_dirty_dbs()
            self._db_dirty = False
        self._db_dirty = False
        self._local_backup_dbs()
        self._last_local_backup = time.time()
        self._last_cloud_full_sync = time.time()
        return {"success": True, "synced_files": self._synced_file_count, "synced_dbs": self._synced_db_count}
