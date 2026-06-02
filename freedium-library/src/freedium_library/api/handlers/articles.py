from beartype import beartype
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Query

from freedium_library.services.recent_posts import (
    RecentPostsResponse,
    RecentPostsService,
)
from freedium_library.services.recent_posts.container import RecentPostsContainer

# All-time unlocked-article count. Refreshed into Redis by the
# refresh_article_count scheduled task (tasks/article_count.py), so this
# endpoint is just a Redis GET shared across all workers.
_ARTICLE_COUNT_KEY = "freedium:article_count"


async def _unlocked_count() -> int:
    """Read the count from Redis (kept warm by refresh_article_count). Cold
    fallback before the first scheduled run: compute from Mongo once and seed
    Redis. Degrades to 0 (→ the banner hides the stat), never 500s."""
    import os

    from redis.asyncio import Redis

    from freedium_library.utils.mongo import get_collection

    r = Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True
    )
    try:
        cached = await r.get(_ARTICLE_COUNT_KEY)
        if cached is not None:
            return int(cached)
        n = int(await get_collection("post_cache").estimated_document_count())
        await r.setex(_ARTICLE_COUNT_KEY, 900, n)  # 900s backstop vs a stuck scheduler
        return n
    except Exception:  # noqa: BLE001
        return 0
    finally:
        await r.aclose()


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

    async def get_random_articles(
        limit: int = Query(
            20, ge=1, le=100, description="Maximum number of random posts to return"
        ),
    ) -> RecentPostsResponse:
        import json
        import os

        from redis.asyncio import Redis

        from freedium_library.services.recent_posts.models import RecentPost

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = Redis.from_url(redis_url, decode_responses=True)
        try:
            raw = await r.get("freedium:random_posts")
            if not raw:
                return RecentPostsResponse(posts=[])
            posts_json_list = json.loads(raw)
            posts = [RecentPost.model_validate_json(p) for p in posts_json_list[:limit]]
            return RecentPostsResponse(posts=posts)
        except Exception:  # noqa: BLE001
            return RecentPostsResponse(posts=[])
        finally:
            await r.aclose()

    articles_router.add_api_route(
        "/random",
        endpoint=get_random_articles,
        methods=["GET"],
        summary="Random posts from the cache",
        description="Returns a random sample of recently-rendered posts, refreshed every 2 minutes.",
        tags=["articles"],
        response_model=RecentPostsResponse,
    )

    async def get_article_count() -> dict[str, int]:
        return {"count": await _unlocked_count()}

    articles_router.add_api_route(
        "/count",
        endpoint=get_article_count,
        methods=["GET"],
        summary="All-time unlocked-article count",
        description="Number of distinct articles Freedium has unlocked (L1 cache size).",
        tags=["articles"],
    )

    router.include_router(articles_router)
