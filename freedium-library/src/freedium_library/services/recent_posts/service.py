from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Iterable

from beartype import beartype
from loguru import logger

from freedium_library.services.medium.renderer import PostMetadata

from .models import RecentPost


_DEFAULT_BUFFER_SIZE = 200


class RecentPostsService:
    """In-memory ring buffer of recently rendered posts.

    Why in-memory: keeps the home-page feed working without requiring an
    operator to provision MongoDB just to run the API. If persistence
    across restarts is needed later, swap the deque for a cache backend
    behind the same async interface — call sites won't change.
    """

    def __init__(self, max_size: int = _DEFAULT_BUFFER_SIZE) -> None:
        self._buffer: deque[RecentPost] = deque(maxlen=max_size)
        self._index: dict[str, RecentPost] = {}
        self._lock = asyncio.Lock()

    @beartype
    async def record(self, metadata: PostMetadata) -> None:
        """Record a freshly rendered post, deduplicating by post_id.

        Re-rendering an article moves it back to the top of the feed
        rather than producing a duplicate entry.
        """
        post = self._from_metadata(metadata)
        if not post.post_id:
            return

        async with self._lock:
            existing = self._index.get(post.post_id)
            if existing is not None:
                try:
                    self._buffer.remove(existing)
                except ValueError:
                    pass
            self._buffer.appendleft(post)
            self._index[post.post_id] = post
            self._prune_index_locked()

        logger.debug(f"RecentPostsService: recorded {post.post_id}")

    @beartype
    async def list(self, limit: int = 20) -> list[RecentPost]:
        """Return the most recently rendered posts, newest first."""
        if limit <= 0:
            return []
        async with self._lock:
            return list(self._iter_first_n(self._buffer, limit))

    def _prune_index_locked(self) -> None:
        """Drop index entries for posts that fell out of the ring buffer."""
        if len(self._index) <= len(self._buffer):
            return
        live_ids = {p.post_id for p in self._buffer}
        for stale_id in [k for k in self._index if k not in live_ids]:
            del self._index[stale_id]

    @staticmethod
    def _iter_first_n(items: Iterable[RecentPost], n: int) -> Iterable[RecentPost]:
        for i, item in enumerate(items):
            if i >= n:
                break
            yield item

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
