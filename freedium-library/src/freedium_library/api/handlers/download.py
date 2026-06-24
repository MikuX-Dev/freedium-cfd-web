"""End-to-end article download: render Medium → resolve gists → file.

Transport-only handler. The render → inline-images → resolve-gists → assemble
domain lives in MarkdownExportService (services/medium/markdown_export.py).
"""

import re

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from loguru import logger

from freedium_library.services.medium.container import MediumContainer
from freedium_library.services.medium.markdown_export import (
    ExportDocument,
    MarkdownExportService,
)


@inject
async def _export(
    url: str,
    export: MarkdownExportService = Provide[MediumContainer.markdown_export],
) -> ExportDocument:
    return await export.to_markdown(url)


def _filename_from_url(url: str) -> str:
    """Derive a .md filename from a URL's last path segment."""
    slug = re.sub(r"\.html?$", "", url.rstrip("/").split("/")[-1].split("?")[0])
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug).strip("-") or "article"
    return f"{slug}.md"


def register_download_router(router: APIRouter) -> None:
    download_router = APIRouter(prefix="/articles")

    async def download_article(
        request: Request,
        url: str = Query(
            ..., description="Article URL or path to render and download."
        ),
    ) -> Response:
        try:
            # Resolve the service so non-Medium sources (NYT, …) download too.
            # Medium keeps its rich export (inline images + gist resolution);
            # other services use their standard frontmatter render.
            resolver = getattr(request.app.state, "service_resolver", None)
            service_name = None
            if resolver is not None:
                try:
                    service_name, service = await resolver.resolve(url)
                except Exception:  # noqa: BLE001 — fall back to medium export
                    service_name = None

            if service_name and service_name != "medium":
                markdown = await service.arender_with_frontmatter(url)
                doc = ExportDocument(
                    content=markdown,
                    filename=_filename_from_url(url),
                    media_type="text/markdown; charset=utf-8",
                )
            else:
                doc = await _export(url)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — boundary handler
            logger.error(f"Download render failed for {url}: {exc}")
            raise HTTPException(
                status_code=502, detail="Failed to render article for download"
            ) from exc

        return Response(
            content=doc.content,
            media_type=doc.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{doc.filename}"',
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
            "into code blocks, and returns the result as a downloadable "
            ".md file. The frontend just needs to navigate to this URL — "
            "the browser handles the download via Content-Disposition."
        ),
        tags=["articles"],
    )

    router.include_router(download_router)
