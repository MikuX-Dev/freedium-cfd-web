from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from freedium_library.api.container import APIContainer
from freedium_library.api.handlers import articles, render
from freedium_library.services.medium.container import MediumContainer
from freedium_library.services.recent_posts.container import RecentPostsContainer
from freedium_library.services.recent_posts.seed_data import get_seed_posts
from freedium_library.services.resolver import ServiceResolver

api_container = APIContainer()
medium_container = MediumContainer()
recent_posts_container = RecentPostsContainer()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.container = api_container
    app.state.medium_container = medium_container
    app.state.recent_posts_container = recent_posts_container
    recent_posts_service = recent_posts_container.service()
    app.state.recent_posts_service = recent_posts_service

    # Pre-populate the recent-posts feed so a fresh boot has something to
    # show on the home page. Real renders push these out as they happen.
    seed_posts = get_seed_posts()
    for metadata in seed_posts:
        await recent_posts_service.record(metadata)
    logger.info(f"Seeded recent-posts feed with {len(seed_posts)} entries")

    # Initialize service resolver
    resolver = ServiceResolver()

    # Register services
    medium_service = medium_container.service()
    resolver.register("medium", medium_service)

    app.state.service_resolver = resolver

    # Wire dependency injection to modules
    medium_container.wire(modules=[render])
    recent_posts_container.wire(modules=[articles])

    yield

    # Unwire on shutdown
    medium_container.unwire()
    recent_posts_container.unwire()
