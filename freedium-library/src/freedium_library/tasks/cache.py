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
async def embed_images_in_cache(url: str, markdown: str, service: str) -> None:
    """Fetch all images from rendered markdown, convert to base64, overwrite L2 cache."""
    import re
    import asyncio
    import base64
    import json

    try:
        import httpx

        img_pattern = re.compile(r'(https://miro\.medium\.com/[^\s")\]]+)')
        urls = list(set(img_pattern.findall(markdown)))

        if not urls:
            return

        # Route image fetches through the same Warp/HAProxy chain that the
        # backend uses so miro.medium.com sees a Cloudflare IP, not the
        # host's. Falls back to direct when PROXY_LIST is unset (dev).
        proxy_url = (os.environ.get("PROXY_LIST", "").split(",")[0].strip() or None)
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, proxy=proxy_url) as client:
            async def fetch_one(img_url: str) -> tuple[str, str | None]:
                try:
                    resp = await client.get(img_url)
                    if resp.status_code == 200:
                        content_type = resp.headers.get("content-type", "image/jpeg")
                        b64 = base64.b64encode(resp.content).decode("ascii")
                        return img_url, f"data:{content_type};base64,{b64}"
                    return img_url, None
                except Exception:
                    return img_url, None

            results = await asyncio.gather(*[fetch_one(u) for u in urls])

        enriched = markdown
        replaced = 0
        for original_url, data_uri in results:
            if data_uri:
                enriched = enriched.replace(original_url, data_uri)
                replaced += 1

        if replaced == 0:
            return

        backend = _get_rendered_backend()
        await backend.apush(url, json.dumps({"markdown": enriched, "service": service}))
        logger.info(f"embed_images_in_cache: embedded {replaced}/{len(urls)} images for {url[:60]}")

    except Exception as exc:
        logger.warning(f"embed_images_in_cache failed for {url[:60]}: {exc!r}")


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
# The handler returns 202 {task_id, status:"pending"} immediately.
# The frontend polls GET /api/render/poll/{task_id} until the task
# finishes and posts the result to Redis.
# ------------------------------------------------------------------

import json as _json
import os as _os
from uuid import uuid4 as _uuid4

import httpx
from loguru import logger as _logger
from redis.asyncio import Redis as _Redis

from freedium_library.api.metrics import ARTICLE_RENDER, ERRORED_LINKS, PDF_RENDER
from freedium_library.services.medium import MediumService
from freedium_library.services.medium.container import MediumContainer
from freedium_library.services.resolver import ServiceResolver
from freedium_library.utils.cache.db.mongo import AsyncMongoDBCacheBackend as _Mongo
from freedium_library.utils.json import json

from . import broker

_RENDER_TTL = 300  # seconds — worst-case render timeout
_REDIS_PREFIX = "freedium:render"


@broker.task
async def render_article_async(content: str, frontmatter: bool, task_id: str) -> None:
    """Full render pipeline for a cold-cache article.

    Runs in the TaskIQ worker so the uvicorn handler can return
    202 Accepted immediately. The result is written to Redis for
    the poll endpoint to serve.
    """

    async def _fail(error_msg: str) -> None:
        r = _Redis.from_url(
            _os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
        try:
            await r.setex(
                f"{_REDIS_PREFIX}:{task_id}", _RENDER_TTL,
                _json.dumps({"status": "error", "error": error_msg[:500]}),
            )
        finally:
            await r.aclose()

    try:
        container = MediumContainer()
        service: MediumService = container.service()
        resolver = ServiceResolver()
        resolver.register("medium", service)

        service_name, resolved_service = await resolver.resolve(content)

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

        # Store in Redis for the poll endpoint
        r = _Redis.from_url(
            _os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
        try:
            await r.setex(
                f"{_REDIS_PREFIX}:{task_id}", _RENDER_TTL,
                _json.dumps(
                    {"markdown": markdown, "service": service_name, "status": "done"}
                ),
            )
        finally:
            await r.aclose()

        # Write L2 cache in background
        from freedium_library.tasks.cache import (
            embed_images_in_cache,
            write_rendered_cache,
        )

        try:
            await write_rendered_cache.kiq(content, markdown, service_name)
            await embed_images_in_cache.kiq(content, markdown, service_name)
        except Exception:
            pass

    except Exception as exc:
        _logger.exception(f"render_article_async failed: {exc!r}")
        await _fail(str(exc))
