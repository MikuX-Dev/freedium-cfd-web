"""One shared async Redis client for the whole process.

Every caller used to run its own `Redis.from_url(os.environ["REDIS_URL"], …)`,
which meant a separate connection pool per module and the default URL spelled
out in six places. `get_redis()` hands out a single lazily-created client, so
connections are pooled once and the URL is configured in exactly one spot.

Returns None when Redis is unreachable — callers treat that as "no cache" /
"feature unavailable" rather than an error.
"""
from __future__ import annotations

import os
from typing import Any

from loguru import logger

REDIS_URL_DEFAULT = "redis://localhost:6379/0"

_client: Any = None
_failed = False


def redis_url() -> str:
    return os.environ.get("REDIS_URL", REDIS_URL_DEFAULT)


def get_redis(url: str | None = None) -> Any:
    """Async Redis client (decode_responses=True), or None if unreachable.

    With no `url`, returns the shared process-wide client — the normal case.
    Passing an explicit `url` returns a dedicated client instead, for callers
    that must target a specific instance (tests, one-off scripts); those own
    its lifecycle and should close it themselves.
    """
    global _client, _failed
    if url is not None:
        try:
            from redis.asyncio import Redis

            return Redis.from_url(url, decode_responses=True)
        except Exception as exc:  # noqa: BLE001 — Redis is always optional
            logger.debug(f"Redis unavailable at {url} ({exc!r})")
            return None

    if _client is None and not _failed:
        try:
            from redis.asyncio import Redis

            _client = Redis.from_url(redis_url(), decode_responses=True)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Redis unavailable ({exc!r})")
            _failed = True
    return _client
