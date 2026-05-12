from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock


class SettingsManager:
    def __init__(self, settings_dir: str | None = None):
        base = Path(settings_dir) if settings_dir else Path(
            os.environ.get("USER_DATA_DIR", Path.home() / ".game-video-tool")
        )
        base.mkdir(parents=True, exist_ok=True)
        self._path = base / "settings.json"
        self._lock = Lock()
        self._data: dict = {}
        self._load()

    def _load(self):
        try:
            if self._path.exists():
                self._data = json.loads(self._path.read_text("utf-8"))
        except Exception:
            self._data = {}

    def _save(self):
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), "utf-8")
        tmp.replace(self._path)

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = value
            self._save()

    def get_all(self) -> dict:
        with self._lock:
            return dict(self._data)
