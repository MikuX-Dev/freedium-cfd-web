"""Scheduled task: refresh the all-time unlocked-article count every 5 min.

Writes freedium:article_count (the post_cache document count) to Redis so the
/api/articles/count endpoint is a single Redis GET — shared across all uvicorn
workers, no Mongo on the request path.
"""
from __future__ import annotations

import os

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from freedium_library.tasks import broker

_REDIS_KEY = "freedium:article_count"


async def _compute_count() -> int:
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    try:
        db = client[os.environ.get("MONGO_DB", "freedium_cache")]
        return int(await db["post_cache"].estimated_document_count())
    finally:
        client.close()


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def refresh_article_count() -> None:
    """Cache the post_cache count in Redis (900s TTL — 3x the cron interval, a
    staleness backstop so a stuck scheduler eventually falls back to Mongo)."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = Redis.from_url(redis_url, decode_responses=True)
    try:
        count = await _compute_count()
        await r.setex(_REDIS_KEY, 900, count)
        logger.info(f"refresh_article_count: cached {count}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"refresh_article_count failed: {exc!r}")
    finally:
        await r.aclose()
