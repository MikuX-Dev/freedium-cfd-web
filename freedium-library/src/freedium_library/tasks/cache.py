"""Background tasks for cache write-back.

These run in the TaskIQ worker process, NOT in the uvicorn request
handler. They receive serialized data, compress it, and write to Mongo.
This removes the 10-50ms cache-write latency from the request path.
"""
from __future__ import annotations

from loguru import logger

from freedium_library.tasks import broker
from freedium_library.utils.cache.db.mongo import AsyncMongoDBCacheBackend
import os


def _get_rendered_backend() -> AsyncMongoDBCacheBackend:
    """Lazy singleton for the worker process."""
    return AsyncMongoDBCacheBackend(
        connection_string=os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
        database=os.environ.get("MONGO_DB", "freedium_cache"),
        collection="rendered_cache",
    )


def _get_graphql_backend() -> AsyncMongoDBCacheBackend:
    """Lazy singleton for the worker process."""
    return AsyncMongoDBCacheBackend(
        connection_string=os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
        database=os.environ.get("MONGO_DB", "freedium_cache"),
        collection=os.environ.get("MONGO_COLLECTION", "post_cache"),
    )


@broker.task
async def write_rendered_cache(url: str, markdown: str, service: str) -> None:
    """Compress and upsert the rendered markdown to Mongo (L2 cache)."""
    try:
        import json
        backend = _get_rendered_backend()
        await backend.apush(url, json.dumps({"markdown": markdown, "service": service}))
    except Exception as exc:
        logger.warning(f"write_rendered_cache failed for {url[:80]}: {exc!r}")


@broker.task
async def write_graphql_cache(post_id: str, data: str) -> None:
    """Compress and upsert the raw GraphQL response to Mongo (L1 cache)."""
    try:
        backend = _get_graphql_backend()
        await backend.apush(post_id, data)
    except Exception as exc:
        logger.warning(f"write_graphql_cache failed for {post_id}: {exc!r}")


@broker.task
async def warm_cache(url: str) -> None:
    """Pre-render a URL so first-time visitors get an L2 hit."""
    try:
        from freedium_library.services.medium.container import MediumContainer
        import json
        container = MediumContainer()
        service = container.service()
        content, _metadata = await service.arender_with_frontmatter_and_metadata(url)
        backend = _get_rendered_backend()
        await backend.apush(url, json.dumps({"markdown": content, "service": "medium"}))
        logger.info(f"warm_cache completed for {url[:80]}")
    except Exception as exc:
        logger.warning(f"warm_cache failed for {url[:80]}: {exc!r}")
