from beartype import beartype
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from loguru import logger

from freedium_library.services.medium import MediumService
from freedium_library.services.medium.container import MediumContainer
from freedium_library.services.medium.renderer import inject_iframe_theme


@beartype
@inject
async def _fetch_iframe(
    iframe_id: str,
    theme: str,
    medium_service: MediumService = Provide[MediumContainer.service],
) -> str:
    """Fetch the iframe HTML for `iframe_id` and bake `theme`-specific CSS in."""
    raw = await medium_service.fetch_iframe_content(iframe_id)
    if not raw:
        raise HTTPException(
            status_code=404, detail=f"No iframe content for id: {iframe_id}"
        )
    return inject_iframe_theme(raw, theme)


def register_iframe_router(router: APIRouter) -> None:
    iframe_router = APIRouter(prefix="/iframe")

    async def get_iframe(
        iframe_id: str,
        theme: str = Query(
            "light",
            pattern="^(light|dark)$",
            description="Theme variant to bake into the returned HTML",
        ),
    ) -> HTMLResponse:
        """Return iframe HTML with theme-specific CSS baked in.

        Used by the frontend to swap iframe srcdoc when the page theme
        toggles, instead of re-rendering the entire article.
        """
        try:
            html = await _fetch_iframe(iframe_id, theme)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — defensive boundary handler
            logger.error(f"Failed to fetch iframe {iframe_id}: {exc}")
            raise HTTPException(status_code=502, detail="Iframe fetch failed") from exc
        return HTMLResponse(content=html, media_type="text/html")

    iframe_router.add_api_route(
        "/{iframe_id}",
        endpoint=get_iframe,
        methods=["GET"],
        summary="Themed iframe HTML",
        description=(
            "Returns the iframe content for the given Medium media id, with "
            "theme-specific CSS baked in. The frontend calls this on theme "
            "toggle to swap iframe srcdoc without re-rendering the article."
        ),
        tags=["iframe"],
        response_class=HTMLResponse,
    )

    router.include_router(iframe_router)
