"""End-to-end article download: render Medium → resolve gists → file."""

import re
from typing import Literal

from beartype import beartype
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from loguru import logger

from freedium_library.services.medium import MediumService
from freedium_library.services.medium.container import MediumContainer
from freedium_library.services.medium.gist_resolver import (
    ResolverMode,
    resolve_gists_in_markdown,
)


_FILENAME_SAFE_RE = re.compile(r"[^a-z0-9]+")


@beartype
def _slugify(title: str | None, fallback: str = "article") -> str:
    if not title:
        return fallback
    slug = _FILENAME_SAFE_RE.sub("-", title.lower()).strip("-")
    return slug or fallback


@beartype
@inject
async def _build_download(
    url: str,
    mode: ResolverMode,
    medium_service: MediumService = Provide[MediumContainer.service],
) -> tuple[str, str]:
    """Render the article, resolve gists, return (markdown, filename)."""
    markdown, metadata = await medium_service.arender_with_metadata(url)
    resolved = await resolve_gists_in_markdown(markdown, mode=mode)
    filename = f"{_slugify(metadata.title)}.md"
    return resolved, filename


def register_download_router(router: APIRouter) -> None:
    download_router = APIRouter(prefix="/articles")

    async def download_article(
        url: str = Query(
            ..., description="Medium article URL or path to render and download."
        ),
        mode: Literal["raw", "rich"] = Query(
            "raw",
            description=(
                "Gist resolution strategy. 'raw' (default) emits bare code "
                "fences via gist.githubusercontent.com/.../raw. 'rich' fetches "
                "each gist's HTML page for filenames + language tags + "
                "multi-file support."
            ),
        ),
    ) -> Response:
        try:
            markdown, filename = await _build_download(url, mode)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — boundary handler
            logger.error(f"Download render failed for {url}: {exc}")
            raise HTTPException(
                status_code=502, detail="Failed to render article for download"
            ) from exc

        return Response(
            content=markdown,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                # Without this, the browser's view of CD is opaque to fetch.
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    download_router.add_api_route(
        "/download",
        endpoint=download_article,
        methods=["GET"],
        summary="Download article as markdown",
        description=(
            "Renders the Medium article, resolves embedded gist iframes "
            "into code blocks via the chosen strategy, and returns the "
            "result as a downloadable .md file. The frontend just needs "
            "to navigate to this URL — the browser handles the download "
            "via Content-Disposition."
        ),
        tags=["articles"],
    )

    router.include_router(download_router)
