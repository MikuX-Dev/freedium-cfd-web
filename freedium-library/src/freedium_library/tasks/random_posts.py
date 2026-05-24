"""Scheduled task: refresh the random-posts cache every 2 minutes."""
from __future__ import annotations

import json
import os

from loguru import logger
from redis.asyncio import Redis

from freedium_library.tasks import broker


@broker.task(schedule=[{"cron": "*/2 * * * *"}])
async def refresh_random_posts() -> None:
    """Sample random posts from the recent-posts pool and cache them.

    Runs on a 2-minute cron via TaskIQ scheduler. Writes to
    freedium:random_posts (JSON array, 130s TTL) so the
    /api/articles/random endpoint is a single Redis GET.
    """
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = Redis.from_url(redis_url, decode_responses=True)

    try:
        post_ids = await r.zrandmember("freedium:recent_posts", count=20)
        if not post_ids:
            logger.debug("refresh_random_posts: no posts in pool")
            return

        post_ids = list(set(post_ids))
        raw_values = await r.hmget("freedium:recent_posts_data", *post_ids)
        posts_json = [v for v in raw_values if v]

        if posts_json:
            await r.setex("freedium:random_posts", 130, json.dumps(posts_json))
            logger.info(f"refresh_random_posts: cached {len(posts_json)} random posts")
    except Exception as exc:
        logger.warning(f"refresh_random_posts failed: {exc!r}")
    finally:
        await r.aclose()
