"""Generic Redis-backed TTL cache with in-flight request de-duplication.

Why this exists: services kept growing their own process-local `dict` caches.
Those never evict (TTL is only checked on read), so they leak — the gist
resolver's cache was the top memory consumer in production.

Redis solves it properly: `SETEX` expires entries natively (no eviction code,
no unbounded growth) and the cache is shared across uvicorn workers *and*
backend replicas instead of being duplicated per process.

Usage:

    _cache = RedisTTLCache(namespace="gist", ttl_seconds=600)

    files = await _cache.get_or_fetch(key, lambda: self._do_fetch(ref))

`get_or_fetch` also collapses concurrent callers for the same key into a
single upstream request. Redis being unavailable degrades to "no caching" —
never an error.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

_MISS = object()

# One shared client (and connection pool) for every cache namespace.
_client: Any = None
_client_failed = False


def _redis() -> Any:
    """Shared async Redis client, or None when Redis isn't reachable."""
    global _client, _client_failed
    if _client is None and not _client_failed:
        try:
            from redis.asyncio import Redis

            _client = Redis.from_url(
                os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
                decode_responses=True,
            )
        except Exception as exc:  # noqa: BLE001 — caching is always optional
            logger.debug(f"RedisTTLCache: Redis unavailable ({exc!r})")
            _client_failed = True
    return _client


@dataclass(slots=True)
class RedisTTLCache:
    """Namespaced TTL cache for JSON-serialisable values.

    `namespace` keeps keys from colliding across services; the stored key is
    ``freedium:{namespace}:{key}``.
    """

    namespace: str
    ttl_seconds: int = 600
    # Only ever holds keys with a fetch currently in flight — the originator
    # pops its entry in a `finally`, so this is bounded by concurrency, not by
    # the number of distinct keys ever seen.
    _inflight: dict[str, asyncio.Task[Any]] = field(
        default_factory=dict, init=False, repr=False
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def _key(self, key: str) -> str:
        return f"freedium:{self.namespace}:{key}"

    async def get(self, key: str) -> Any:
        """Cached value, or the `MISS` sentinel. A cached `None` is a hit."""
        redis = _redis()
        if redis is None:
            return _MISS
        try:
            raw = await redis.get(self._key(key))
            return _MISS if raw is None else json.loads(raw)
        except Exception as exc:  # noqa: BLE001 — any failure is just a miss
            logger.debug(f"cache[{self.namespace}] read failed: {exc!r}")
            return _MISS

    async def set(self, key: str, value: Any) -> None:
        redis = _redis()
        if redis is None:
            return
        try:
            await redis.setex(self._key(key), self.ttl_seconds, json.dumps(value))
        except Exception as exc:  # noqa: BLE001 — a write must never break the caller
            logger.debug(f"cache[{self.namespace}] write failed: {exc!r}")

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        """Return the cached value, else run `fetcher` once and cache it.

        Concurrent callers for the same key await a single shared task.
        """
        cached = await self.get(key)
        if cached is not _MISS:
            return cached

        async with self._lock:
            task = self._inflight.get(key)
            is_originator = task is None
            if is_originator:
                task = asyncio.create_task(fetcher())
                self._inflight[key] = task
        assert task is not None

        if not is_originator:
            return await task
        try:
            value = await task
        finally:
            # Drop the in-flight entry even if the fetch raised, so one
            # failure can't wedge every later request for the same key.
            async with self._lock:
                self._inflight.pop(key, None)
        await self.set(key, value)
        return value


#: Sentinel returned by `RedisTTLCache.get` when a key isn't cached.
MISS = _MISS
