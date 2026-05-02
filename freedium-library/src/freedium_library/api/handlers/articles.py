from beartype import beartype
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Query

from freedium_library.services.recent_posts import (
    RecentPostsResponse,
    RecentPostsService,
)
from freedium_library.services.recent_posts.container import RecentPostsContainer


@beartype
@inject
async def _list_recent_articles(
    limit: int,
    recent_posts_service: RecentPostsService = Provide[RecentPostsContainer.service],
) -> RecentPostsResponse:
    """DI-wired implementation. Wrapped by an HTTP-friendly endpoint so FastAPI
    doesn't try to interpret the injected service as a request parameter."""
    posts = await recent_posts_service.list(limit=limit)
    return RecentPostsResponse(posts=posts)


def register_articles_router(router: APIRouter) -> None:
    articles_router = APIRouter(prefix="/articles")

    async def get_recent_articles(
        limit: int = Query(
            20, ge=1, le=100, description="Maximum number of posts to return"
        ),
    ) -> RecentPostsResponse:
        return await _list_recent_articles(limit=limit)

    articles_router.add_api_route(
        "/recent",
        endpoint=get_recent_articles,
        methods=["GET"],
        summary="Recently unlocked articles",
        description=(
            "Returns posts that have been rendered through Freedium recently. "
            "Used to populate the home-page feed."
        ),
        tags=["articles"],
        response_model=RecentPostsResponse,
    )

    router.include_router(articles_router)
