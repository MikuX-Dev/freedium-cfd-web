import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from freedium_library.api.container import APIContainer
from freedium_library.api.handlers import articles, download, render
from freedium_library.services.medium import MediumService
from freedium_library.services.medium.container import MediumContainer
from freedium_library.services.recent_posts.container import RecentPostsContainer
from freedium_library.services.recent_posts.seed_urls import SEED_URLS
from freedium_library.services.recent_posts.service import RecentPostsService
from freedium_library.services.resolver import ServiceResolver

api_container = APIContainer()
medium_container = MediumContainer()
recent_posts_container = RecentPostsContainer()


async def _warmup_recent_feed(
    medium_service: MediumService,
    recent_posts_service: RecentPostsService,
    urls: list[str],
) -> None:
    """Render each seed URL through the medium service and record the
    resulting metadata into the recent-posts feed. Best-effort: any URL
    that fails (Medium unreachable, post deleted, etc.) is logged and
    skipped — warmup is non-essential, so we never crash the app over it.
    """
    if not urls:
        return
    logger.info(f"Warming up recent-posts feed from {len(urls)} URL(s)")
    for url in urls:
        try:
            _, metadata = await medium_service.arender_with_metadata(url)
            await recent_posts_service.record(metadata)
            logger.info(f"Warmup: recorded {metadata.post_id} ({metadata.title[:60]})")
        except Exception as exc:  # noqa: BLE001 — best-effort; never crash on warmup
            logger.warning(f"Warmup failed for {url}: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.container = api_container
    app.state.medium_container = medium_container
    app.state.recent_posts_container = recent_posts_container
    recent_posts_service = recent_posts_container.service()
    app.state.recent_posts_service = recent_posts_service

    # Initialize service resolver
    resolver = ServiceResolver()

    # Register services
    medium_service = medium_container.service()
    resolver.register("medium", medium_service)

    app.state.service_resolver = resolver

    # Wire dependency injection to modules
    medium_container.wire(modules=[download, render])
    recent_posts_container.wire(modules=[articles])

    # Warm up the recent-posts feed in the background so the home page
    # shows real article metadata when Medium is reachable. Non-blocking:
    # the API starts serving immediately even while warmup is in flight.
    warmup_task = asyncio.create_task(
        _warmup_recent_feed(medium_service, recent_posts_service, SEED_URLS)
    )

    yield

    # Cancel any in-flight warmup so it doesn't outlive the app
    if not warmup_task.done():
        warmup_task.cancel()
        try:
            await warmup_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    # Unwire on shutdown
    medium_container.unwire()
    recent_posts_container.unwire()
