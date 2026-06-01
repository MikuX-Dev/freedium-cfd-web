"""End-to-end article download: render Medium → resolve gists → file.

Transport-only handler. The render → inline-images → resolve-gists → assemble
domain lives in MarkdownExportService (services/medium/markdown_export.py).
"""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, HTTPException, Query
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


def register_download_router(router: APIRouter) -> None:
    download_router = APIRouter(prefix="/articles")

    async def download_article(
        url: str = Query(
            ..., description="Medium article URL or path to render and download."
        ),
    ) -> Response:
        try:
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
