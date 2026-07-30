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


# ------------------------------------------------------------------
# Cold-render task — dispatched by render_universal when BOTH L2 and
# L1 caches miss. Runs inside the TaskIQ worker so uvicorn workers
# never block on a 20-60s Medium GraphQL fetch through WARP.
#
# Uses TaskIQ's built-in result backend (RedisAsyncResultBackend) —
# the result is stored automatically via the broker's return-value
# mechanism. No manual Redis keys needed.
# ------------------------------------------------------------------

from freedium_library.services.medium.container import MediumContainer
from freedium_library.services.resolver import ServiceResolver

from . import broker


@broker.task
async def render_article_async(content: str, frontmatter: bool) -> dict:
    """Full render pipeline for a cold-cache article.

    Returns {"markdown": ..., "service": ...} which TaskIQ stores in
    the configured RedisAsyncResultBackend. The caller waits via
    task.wait_result() and the poll endpoint reads via
    result_backend.get_result(task_id).

    A plain Exception raised here becomes `result.is_err = True`.
    The poll endpoint surfaces a user-safe error message.
    """
    container = MediumContainer()
    service = container.service()
    resolver = ServiceResolver()

    from freedium_library.api.config import MediumConfig, NytConfig

    # Specific-host services FIRST; Medium last (permissive validator).
    _nyt_cfg = NytConfig()
    if _nyt_cfg.ENABLED:
        import os

        from freedium_library.services.nyt import NytService
        from freedium_library.services.nyt import client as _nyt_client

        if _nyt_client._NYT_PRIVATE_KEY is not None:
            _proxy = os.environ.get("PROXY_LIST", "").split(",")[0].strip() or None
            resolver.register("nyt", NytService(proxy=_proxy, mdream_url=_nyt_cfg.MDREAM_URL))

    from freedium_library.api.config import WapoConfig

    if WapoConfig().ENABLED:
        from freedium_library.services.wapo import WapoService

        resolver.register("wapo", WapoService())

    from freedium_library.api.config import FtConfig

    if FtConfig().ENABLED:
        from freedium_library.services.ft import FtService

        resolver.register("ft", FtService())

    from freedium_library.api.config import EconomistConfig

    if EconomistConfig().ENABLED:
        from freedium_library.services.economist import EconomistService

        resolver.register("economist", EconomistService())

    from freedium_library.api.config import ReutersConfig

    if ReutersConfig().ENABLED:
        from freedium_library.services.reuters import ReutersService

        _reuters_proxy = os.environ.get("PROXY_LIST", "").split(",")[0].strip() or None
        resolver.register("reuters", ReutersService(proxy=_reuters_proxy))

    from freedium_library.api.config import BloombergConfig

    if BloombergConfig().ENABLED:
        from freedium_library.services.bloomberg import BloombergService

        resolver.register("bloomberg", BloombergService())

    # Medium LAST — permissive validator (accepts any URL).
    if MediumConfig().ENABLED:
        resolver.register("medium", service)

    service_name, resolved_service = await resolver.resolve(content)

    # Cap concurrent renders in the worker too: a burst of dispatched
    # render tasks otherwise runs all at once and saturates the CPU. The
    # semaphore makes excess work queue instead of thrash.
    from freedium_library.api.render_limit import render_semaphore

    async with render_semaphore:
        if service_name == "medium":
            if frontmatter:
                markdown, _metadata = (
                    await service.arender_with_frontmatter_and_metadata(content)
                )
            else:
                markdown, _metadata = await service.arender_with_metadata(content)
        else:
            markdown = (
                await resolved_service.arender_with_frontmatter(content)
                if frontmatter
                else await resolved_service.arender(content)
            )

    # Write L2 cache in background
    from freedium_library.tasks.cache import write_rendered_cache

    try:
        await write_rendered_cache.kiq(content, markdown, service_name)
    except Exception:
        pass

    return {"markdown": markdown, "service": service_name}
