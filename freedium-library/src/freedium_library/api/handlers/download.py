"""End-to-end article download: render Medium → resolve gists → file."""

import os
import re
from collections.abc import Iterable

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
from freedium_library.services.medium.renderer import PostMetadata

# Strategy used for gist resolution on the download path. Switch to "rich"
# to embed filename headers, language tags, and multi-file gists at the
# cost of one extra HTTP request per gist. Both resolvers remain available
# as services in `gist_resolver` — only the download endpoint is pinned.
_GIST_MODE: ResolverMode = "raw"

_FILENAME_SAFE_RE = re.compile(r"[^a-z0-9]+")

_PUBLIC_URL = os.environ.get("FREEDIUM_PUBLIC_URL", "https://freedium-mirror.cfd").rstrip("/")


@beartype
def _slugify(title: str | None, fallback: str = "article") -> str:
    if not title:
        return fallback
    slug = _FILENAME_SAFE_RE.sub("-", title.lower()).strip("-")
    return slug or fallback


def _yaml_quote(value: str) -> str:
    """Double-quoted YAML scalar safe for arbitrary text."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


@beartype
def _build_frontmatter(metadata: PostMetadata) -> str:
    """YAML frontmatter with title, subtitle, tags. Skips empty fields so
    consumers don't see `subtitle: ""` for articles that don't have one."""
    lines: list[str] = ["---"]
    if metadata.title:
        lines.append(f"title: {_yaml_quote(metadata.title)}")
    if metadata.subtitle:
        lines.append(f"subtitle: {_yaml_quote(metadata.subtitle)}")
    tags: Iterable[str] = (t for t in metadata.tags if t)
    rendered_tags = [_yaml_quote(t) for t in tags]
    if rendered_tags:
        lines.append(f"tags: [{', '.join(rendered_tags)}]")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


@beartype
@inject
async def _build_download(
    url: str,
    medium_service: MediumService = Provide[MediumContainer.service],
) -> tuple[str, str]:
    """Render the article, resolve gists, prepend frontmatter, return
    (markdown, filename)."""
    markdown, metadata = await medium_service.arender_with_metadata(url)
    resolved = await resolve_gists_in_markdown(markdown, mode=_GIST_MODE)
    source_url = (getattr(metadata, "medium_url", "") or url)
    freedium_link = f"{_PUBLIC_URL}/{source_url}"
    link_block = f"> 📖 Read on Freedium: {freedium_link}\n>\n> 🔗 Original: {source_url}\n"
    body = _build_frontmatter(metadata) + "\n" + link_block + "\n" + resolved
    filename = f"{_slugify(metadata.title)}.md"
    return body, filename


def register_download_router(router: APIRouter) -> None:
    download_router = APIRouter(prefix="/articles")

    async def download_article(
        url: str = Query(
            ..., description="Medium article URL or path to render and download."
        ),
    ) -> Response:
        try:
            markdown, filename = await _build_download(url)
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
            "into code blocks, and returns the result as a downloadable "
            ".md file. The frontend just needs to navigate to this URL — "
            "the browser handles the download via Content-Disposition."
        ),
        tags=["articles"],
    )

    router.include_router(download_router)
