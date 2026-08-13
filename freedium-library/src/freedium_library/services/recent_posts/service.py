from __future__ import annotations

import os
import time

from beartype import beartype
from loguru import logger
from redis.asyncio import Redis

from freedium_library.utils.cache.redis_client import get_redis

from freedium_library.services.medium.renderer import PostMetadata
from .models import RecentPost


_DEFAULT_BUFFER_SIZE = 200
_SORTED_SET_KEY = "freedium:recent_posts"
_HASH_KEY = "freedium:recent_posts_data"


class RecentPostsService:
    """Redis-backed ring buffer of recently rendered posts.

    Uses a sorted set (scores = unlocked_at timestamps) for ordering
    and deduplication, plus a hash for the full post data. Shared
    across all uvicorn workers via the stack's Redis instance.

    Falls back to a no-op if Redis is unreachable — the home page
    shows "no recent unlocks" rather than crashing.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        max_size: int = _DEFAULT_BUFFER_SIZE,
    ) -> None:
        self._max_size = max_size
        # None → the shared process-wide client; an explicit url → a dedicated
        # one (see get_redis).
        self._redis: Redis = get_redis(redis_url)

    @beartype
    async def record(self, metadata: PostMetadata) -> None:
        """Record a freshly rendered post, deduplicating by post_id.

        Re-rendering an article moves it back to the top of the feed
        rather than producing a duplicate entry.
        """
        post = self._from_metadata(metadata)
        if not post.post_id:
            return

        try:
            pipe = self._redis.pipeline()
            now = post.unlocked_at or int(time.time() * 1000)
            pipe.zadd(_SORTED_SET_KEY, {post.post_id: now})
            pipe.hset(_HASH_KEY, post.post_id, post.model_dump_json())
            # Trim oldest entries beyond max_size
            pipe.zremrangebyrank(_SORTED_SET_KEY, 0, -(self._max_size + 1))
            await pipe.execute()
            logger.debug(f"RecentPostsService: recorded {post.post_id}")
        except Exception as exc:
            logger.warning(f"RecentPostsService.record failed: {exc!r}")

    @beartype
    async def list(self, limit: int = 20) -> list[RecentPost]:
        """Return the most recently rendered posts, newest first."""
        if limit <= 0:
            return []
        try:
            post_ids = await self._redis.zrevrange(_SORTED_SET_KEY, 0, limit - 1)
            if not post_ids:
                return []
            raw_values = await self._redis.hmget(_HASH_KEY, *post_ids)
            posts = []
            for raw in raw_values:
                if raw:
                    posts.append(RecentPost.model_validate_json(raw))
            return posts
        except Exception as exc:
            logger.warning(f"RecentPostsService.list failed: {exc!r}")
            return []

    @staticmethod
    def _from_metadata(metadata: PostMetadata) -> RecentPost:
        return RecentPost(
            post_id=metadata.post_id,
            title=metadata.title,
            subtitle=metadata.subtitle,
            creator_name=metadata.creator_name,
            creator_avatar_id=metadata.creator_avatar_id,
            collection_name=metadata.collection_name,
            reading_time=metadata.reading_time,
            first_published_at=metadata.first_published_at,
            preview_image_id=metadata.preview_image_id,
            medium_url=metadata.medium_url,
            tags=list(metadata.tags),
            unlocked_at=int(time.time() * 1000),
        )
