from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from freedium_library.api.container import APIContainer
from freedium_library.api.handlers import articles, render
from freedium_library.services.medium.container import MediumContainer
from freedium_library.services.recent_posts.container import RecentPostsContainer
from freedium_library.services.resolver import ServiceResolver

api_container = APIContainer()
medium_container = MediumContainer()
recent_posts_container = RecentPostsContainer()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.container = api_container
    app.state.medium_container = medium_container
    app.state.recent_posts_container = recent_posts_container
    app.state.recent_posts_service = recent_posts_container.service()

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
