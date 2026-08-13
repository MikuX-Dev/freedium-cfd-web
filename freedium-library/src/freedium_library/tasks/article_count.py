"""Scheduled task: refresh the all-time unlocked-article count every 5 min.

Writes freedium:article_count (the post_cache document count) to Redis so the
/api/articles/count endpoint is a single Redis GET — shared across all uvicorn
workers, no Mongo on the request path.
"""
from __future__ import annotations


from loguru import logger
from freedium_library.utils.cache.redis_client import get_redis

from freedium_library.tasks import broker
from freedium_library.utils.mongo import get_collection

_REDIS_KEY = "freedium:article_count"


async def _compute_count() -> int:
    return int(await get_collection("post_cache").estimated_document_count())


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def refresh_article_count() -> None:
    """Cache the post_cache count in Redis (900s TTL — 3x the cron interval, a
    staleness backstop so a stuck scheduler eventually falls back to Mongo)."""
    r = get_redis()
    if r is None:
        return
    try:
        count = await _compute_count()
        await r.setex(_REDIS_KEY, 900, count)
        logger.info(f"refresh_article_count: cached {count}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"refresh_article_count failed: {exc!r}")
    # NB: no aclose() — the client is shared process-wide.
