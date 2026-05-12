"""Provider status-query throttling for task polling.

This limiter is intentionally separate from the provider generation queue:
polling must not consume generation slots, and generation must not be delayed by
many browser tabs asking the same provider for task state.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from provider_queue import PROVIDER_LABELS, normalize_provider_key


class StatusQueryBusyError(Exception):
    """Raised when provider task-status polling is saturated."""


PROCESSING_STATUSES = {"pending", "processing", "running", "queued", "queueing", "submitted", "in_progress"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "")
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "")
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _status_query_limit(provider_key: str) -> int:
    defaults = {
        "ark": 2,
        "dashscope": 1,
        "vidu": 1,
        "default": 2,
    }
    specific_name = f"GAME_STATUS_QUERY_{provider_key.upper()}_CONCURRENCY"
    default_limit = _env_int("GAME_STATUS_QUERY_DEFAULT_CONCURRENCY", defaults.get(provider_key, 2))
    return max(1, _env_int(specific_name, default_limit))


def _status_query_timeout_seconds() -> float:
    return max(0.1, _env_float("GAME_STATUS_QUERY_QUEUE_TIMEOUT_SECONDS", 2.0))


def _processing_ttl_seconds() -> float:
    return max(0.0, _env_float("GAME_STATUS_QUERY_PROCESSING_TTL_SECONDS", 3.0))


def is_processing_status(status: str) -> bool:
    return (status or "").lower() in PROCESSING_STATUSES


def status_query_busy_result(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "status": "processing",
        "message": "状态查询排队中，请稍后自动刷新",
    }


def _clone_result(result: dict) -> dict:
    return dict(result or {})


class StatusQueryLimiter:
    def __init__(self, provider_key: str):
        self.provider_key = provider_key
        self.limit = _status_query_limit(provider_key)
        self.semaphore = asyncio.Semaphore(self.limit)
        self.lock = asyncio.Lock()
        self.inflight: dict[str, asyncio.Task] = {}
        self.processing_cache: dict[str, tuple[float, dict]] = {}
        self.active = 0
        self.waiting = 0
        self.total_started = 0
        self.total_completed = 0
        self.total_timeouts = 0
        self.total_cache_hits = 0
        self.total_coalesced = 0
        self.created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _cache_get_locked(self, task_id: str, now: float) -> dict | None:
        cached = self.processing_cache.get(task_id)
        if not cached:
            return None
        expires_at, result = cached
        if expires_at <= now:
            self.processing_cache.pop(task_id, None)
            return None
        self.total_cache_hits += 1
        return _clone_result(result)

    def _prune_cache_locked(self, now: float) -> None:
        expired = [task_id for task_id, (expires_at, _result) in self.processing_cache.items() if expires_at <= now]
        for task_id in expired:
            self.processing_cache.pop(task_id, None)

    async def _run_provider_query(self, task_id: str, fn: Callable[[], Awaitable[dict]]) -> dict:
        timeout = _status_query_timeout_seconds()
        self.waiting += 1
        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            self.total_timeouts += 1
            label = PROVIDER_LABELS.get(self.provider_key, self.provider_key)
            raise StatusQueryBusyError(f"{label}状态查询排队超过 {timeout:.1f} 秒，请稍后自动刷新。") from exc
        finally:
            self.waiting = max(0, self.waiting - 1)

        self.active += 1
        self.total_started += 1
        try:
            result = await fn()
            result = _clone_result(result)
            result.setdefault("task_id", task_id)
            if is_processing_status(str(result.get("status", ""))):
                ttl = _processing_ttl_seconds()
                if ttl > 0:
                    async with self.lock:
                        self.processing_cache[task_id] = (time.monotonic() + ttl, _clone_result(result))
            return result
        finally:
            self.active = max(0, self.active - 1)
            self.total_completed += 1
            self.semaphore.release()

    async def run(self, task_id: str, fn: Callable[[], Awaitable[dict]]) -> dict:
        now = time.monotonic()
        async with self.lock:
            cached = self._cache_get_locked(task_id, now)
            if cached is not None:
                return cached
            existing = self.inflight.get(task_id)
            if existing is not None:
                self.total_coalesced += 1
                task = existing
            else:
                task = asyncio.create_task(self._run_provider_query(task_id, fn))
                self.inflight[task_id] = task

        try:
            return _clone_result(await task)
        finally:
            async with self.lock:
                if self.inflight.get(task_id) is task:
                    self.inflight.pop(task_id, None)
                self._prune_cache_locked(time.monotonic())

    def snapshot(self) -> dict:
        now = time.monotonic()
        return {
            "label": PROVIDER_LABELS.get(self.provider_key, self.provider_key),
            "active": self.active,
            "waiting": self.waiting,
            "limit": self.limit,
            "available": max(0, self.limit - self.active),
            "saturated": self.active >= self.limit,
            "inflight": len(self.inflight),
            "cache_entries": sum(1 for expires_at, _result in self.processing_cache.values() if expires_at > now),
            "processing_ttl_seconds": _processing_ttl_seconds(),
            "queue_timeout_seconds": _status_query_timeout_seconds(),
            "total_started": self.total_started,
            "total_completed": self.total_completed,
            "total_timeouts": self.total_timeouts,
            "total_cache_hits": self.total_cache_hits,
            "total_coalesced": self.total_coalesced,
            "created_at": self.created_at,
        }


_limiters: dict[str, StatusQueryLimiter] = {}


def get_status_query_limiter(provider: str) -> StatusQueryLimiter:
    provider_key = normalize_provider_key(provider)
    limiter = _limiters.get(provider_key)
    if limiter is None:
        limiter = StatusQueryLimiter(provider_key)
        _limiters[provider_key] = limiter
    return limiter


async def run_status_query(provider: str, task_id: str, fn: Callable[[], Awaitable[dict]]) -> dict:
    return await get_status_query_limiter(provider).run(task_id, fn)


def status_query_snapshot() -> dict:
    return {
        "providers": {
            key: limiter.snapshot()
            for key, limiter in sorted(_limiters.items())
        }
    }


def reset_status_query_state_for_tests() -> None:
    _limiters.clear()
