"""End-to-end article download: render Medium → resolve gists → file."""

import asyncio
import os
import re
from collections.abc import Iterable

import httpx
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
from freedium_library.services.pdf.image_inliner import _fetch_one, _fetch_url_for_src

# Strategy used for gist resolution on the download path. Switch to "rich"
# to embed filename headers, language tags, and multi-file gists at the
# cost of one extra HTTP request per gist. Both resolvers remain available
# as services in `gist_resolver` — only the download endpoint is pinned.
_GIST_MODE: ResolverMode = "raw"

_FILENAME_SAFE_RE = re.compile(r"[^a-z0-9]+")

_PUBLIC_URL = os.environ.get("FREEDIUM_PUBLIC_URL", "https://freedium-mirror.cfd").rstrip("/")

# The renderer emits images as <picture> HTML referencing our /img proxy.
# For a portable, self-contained .md we replace each block with a plain
# Markdown image whose source is a base64 data: URI.
_PICTURE_RE = re.compile(r"<picture>.*?</picture>", re.DOTALL)
_IMG_SRC_RE = re.compile(r'<img\s+src="(/img/\d+/[^"]+|https?://[^"]+)"')
_ALT_RE = re.compile(r'alt="([^"]*)"')


async def _inline_images_as_base64_markdown(markdown: str) -> str:
    """Replace each <picture> block with ![alt](data:...;base64,...).

    Downloads each image (through the WARP proxy, like the PDF inliner) and
    base64-embeds it so the exported Markdown is self-contained and contains
    no HTML or remote/relative image URLs. Failed fetches become a 1x1
    placeholder rather than breaking the export.
    """
    blocks = _PICTURE_RE.findall(markdown)
    if not blocks:
        return markdown

    # block -> (alt, fetch_url); dedupe fetches by URL.
    jobs: list[tuple[str, str, str]] = []  # (block, alt, fetch_url)
    fetch_urls: dict[str, None] = {}
    for block in blocks:
        m_src = _IMG_SRC_RE.search(block)
        if not m_src:
            continue
        fetch_url = _fetch_url_for_src(m_src.group(1))
        if not fetch_url:
            continue
        m_alt = _ALT_RE.search(block)
        alt = (m_alt.group(1) if m_alt else "").replace("]", "").replace("[", "")
        jobs.append((block, alt, fetch_url))
        fetch_urls[fetch_url] = None

    if not jobs:
        return markdown

    proxy_url = os.environ.get("PROXY_LIST", "").split(",")[0].strip() or None
    sem = asyncio.Semaphore(8)
    urls = list(fetch_urls)
    async with httpx.AsyncClient(follow_redirects=True, proxy=proxy_url) as client:
        results = await asyncio.gather(*(_fetch_one(client, u, sem) for u in urls))
    data_by_url = dict(zip(urls, results))

    out = markdown
    for block, alt, fetch_url in jobs:
        data_uri = data_by_url.get(fetch_url, "")
        out = out.replace(block, f"![{alt}]({data_uri})", 1)
    return out


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
    # Embed images as base64 so the .md is self-contained (no <picture> HTML
    # / relative proxy URLs).
    markdown = await _inline_images_as_base64_markdown(markdown)
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
