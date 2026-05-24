from beartype import beartype
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from loguru import logger
from pydantic import BaseModel

from freedium_library.api.error_log import log_errored_link
from freedium_library.api.metrics import (
    ARTICLE_RENDER,
    RENDERED_CACHE_HITS,
    RENDERED_CACHE_MISSES,
    track_render,
)
from freedium_library.services.medium import MediumService
from freedium_library.services.medium.container import MediumContainer
from freedium_library.services.medium.exceptions import InvalidMediumServicePathError
from freedium_library.services.recent_posts import RecentPostsService
from freedium_library.services.resolver import ServiceResolver, ServiceResolutionError


class RenderRequest(BaseModel):
    """Request body for universal render endpoint."""

    content: str
    frontmatter: bool = False


class RenderResponse(BaseModel):
    """Response from render endpoint."""

    markdown: str
    service: str
    cache_status: str = "miss"


async def _record_recent(
    request: Request | None, metadata: object
) -> None:
    """Push a rendered post's metadata into the recent-posts feed.

    Best-effort: any failure (no service wired up, lock contention, etc.)
    must never break the render response — recent posts is decorative.
    The service is read off app.state because it's instantiated by the
    lifespan singleton, not the per-request DI container.
    """
    if request is None:
        return
    service: RecentPostsService | None = getattr(
        request.app.state, "recent_posts_service", None
    )
    if service is None:
        return
    try:
        await service.record(metadata)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 — defensive: never break render
        logger.warning(f"Failed to record recent post: {exc}")


@beartype
@inject
async def render_medium_post(
    post_id: str,
    include_frontmatter: bool = False,
    request: Request | None = None,
    medium_service: MediumService = Provide[MediumContainer.service],
) -> PlainTextResponse:
    """
    Render a Medium post to Markdown format.

    Args:
        post_id: The Medium post ID or URL to render
        include_frontmatter: Whether to include YAML frontmatter
        request: The HTTP request (used to access app state for recent-posts feed)
        medium_service: The Medium service instance (injected)

    Returns:
        Rendered Markdown content
    """
    with track_render(ARTICLE_RENDER) as ctx:
        try:
            # Use the *_and_metadata variants so we capture PostMetadata in the same
            # GraphQL fetch — no extra round-trip just for the recent-posts feed.
            if include_frontmatter:
                content, metadata = (
                    await medium_service.arender_with_frontmatter_and_metadata(post_id)
                )
            else:
                content, metadata = await medium_service.arender_with_metadata(post_id)

            await _record_recent(request, metadata)
            return PlainTextResponse(content=content, media_type="text/markdown")

        except InvalidMediumServicePathError as e:
            ctx.set_outcome("parser_failure")
            log_errored_link(post_id, "parser_failure", None, str(e))
            raise HTTPException(status_code=404, detail=str(e)) from e


@beartype
async def render_universal(
    http_request: Request,
    request: RenderRequest,
) -> RenderResponse:
    """
    Universal render endpoint that detects service and renders content.

    Args:
        http_request: The HTTP request object (contains app state)
        request: Request containing content string and options

    Returns:
        Rendered markdown and service name

    Raises:
        HTTPException 404: If no service can handle the content
        HTTPException 500: If rendering fails
    """
    # --- L2: rendered-output cache ---
    import json as _json

    rendered_cache = getattr(http_request.app.state, "rendered_cache", None)
    if rendered_cache is not None:
        try:
            cached = await rendered_cache.apull(request.content)
            if cached is not None:
                data = _json.loads(cached.value)
                RENDERED_CACHE_HITS.inc()
                has_embedded = "data:image" in data["markdown"]
                return RenderResponse(
                    markdown=data["markdown"],
                    service=data["service"],
                    cache_status=f"l2_hit_{'embedded' if has_embedded else 'cdn'}",
                )
        except Exception:
            pass  # treat L2 read failure as a miss
    RENDERED_CACHE_MISSES.inc()

    with track_render(ARTICLE_RENDER) as ctx:
        try:
            # Get resolver from app state
            resolver: ServiceResolver = http_request.app.state.service_resolver

            # Resolve the content to appropriate service
            service_name, service = await resolver.resolve(request.content)

            # Render using the resolved service. For Medium, use the *_and_metadata
            # variants so we can populate the recent-posts feed in the same GraphQL
            # fetch — no extra round-trip just for feed data.
            if service_name == "medium" and isinstance(service, MediumService):
                if request.frontmatter:
                    markdown, metadata = (
                        await service.arender_with_frontmatter_and_metadata(request.content)
                    )
                else:
                    markdown, metadata = await service.arender_with_metadata(request.content)
                await _record_recent(http_request, metadata)
            else:
                if request.frontmatter:
                    markdown = await service.arender_with_frontmatter(request.content)
                else:
                    markdown = await service.arender(request.content)

            # Write to L2 rendered cache (async via TaskIQ)
            if rendered_cache is not None:
                from freedium_library.tasks.cache import write_rendered_cache, embed_images_in_cache
                try:
                    await write_rendered_cache.kiq(request.content, markdown, service_name)
                    # Background: fetch images, convert to base64, overwrite L2 cache
                    await embed_images_in_cache.kiq(request.content, markdown, service_name)
                except Exception:
                    pass  # broker down — fall through silently

            return RenderResponse(markdown=markdown, service=service_name)

        except ServiceResolutionError as e:
            ctx.set_outcome("parser_failure")
            log_errored_link(request.content, "parser_failure", None, str(e))
            raise HTTPException(status_code=404, detail=str(e)) from e
        except InvalidMediumServicePathError as e:
            ctx.set_outcome("parser_failure")
            log_errored_link(request.content, "parser_failure", None, str(e))
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            ctx.set_outcome("network_error")
            log_errored_link(request.content, "network_error", None, str(e))
            raise HTTPException(
                status_code=500,
                detail=f"Error rendering content: {str(e)}",
            ) from e


def register_render_router(router: APIRouter) -> None:
    render_router = APIRouter(prefix="/render")

    # Universal endpoint - detects service automatically
    render_router.add_api_route(
        "",
        endpoint=render_universal,
        methods=["POST"],
        summary="Render content (universal)",
        description="Render any supported content type to Markdown. Automatically detects the service.",
        tags=["render"],
        response_model=RenderResponse,
    )

    # Legacy Medium-specific endpoint (kept for backwards compatibility)
    async def _render_medium(
        request: Request,
        post_id: str,
        frontmatter: bool = Query(False, description="Include YAML frontmatter"),
    ) -> PlainTextResponse:
        return await render_medium_post(
            post_id, include_frontmatter=frontmatter, request=request
        )

    render_router.add_api_route(
        "/medium/{post_id:path}",
        endpoint=_render_medium,
        methods=["GET"],
        summary="Render Medium post",
        description="Render a Medium post to Markdown format (legacy endpoint)",
        tags=["render"],
        response_class=PlainTextResponse,
    )

    router.include_router(render_router)
