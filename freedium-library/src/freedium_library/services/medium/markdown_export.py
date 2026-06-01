"""Markdown export domain: render a Medium article into a self-contained .md.

Owns the render → inline-images → resolve-gists → assemble flow and returns an
ExportDocument value object. The transport handler (api/handlers/download.py)
just turns that into an HTTP Response.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import httpx
import yaml
from beartype import beartype

from freedium_library.services.medium.gist_resolver import (
    ResolverMode,
    resolve_gists_in_markdown,
)
from freedium_library.services.medium.image_fetcher import (
    fetch_as_data_uri,
    fetch_url_for_src,
    proxy_url_from_env,
)
from freedium_library.services.medium.medium import MediumService
from freedium_library.services.medium.renderer import PostMetadata

_FILENAME_SAFE_RE = re.compile(r"[^a-z0-9]+")

# The renderer emits images as <picture> HTML referencing our /img proxy.
# For a portable, self-contained .md we replace each block with a plain
# Markdown image whose source is a base64 data: URI.
_PICTURE_RE = re.compile(r"<picture>.*?</picture>", re.DOTALL)
_IMG_SRC_RE = re.compile(r'<img\s+src="(/img/\d+/[^"]+|https?://[^"]+)"')
_ALT_RE = re.compile(r'alt="([^"]*)"')


@dataclass(slots=True)
class ExportDocument:
    """A rendered, self-contained markdown document ready to be served."""

    content: str
    filename: str
    media_type: str


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
        fetch_url = fetch_url_for_src(m_src.group(1))
        if not fetch_url:
            continue
        m_alt = _ALT_RE.search(block)
        alt = m_alt.group(1) if m_alt else ""
        if alt == "None":  # renderer emits alt="None" when alt is absent
            alt = ""
        alt = alt.replace("]", "").replace("[", "")
        jobs.append((block, alt, fetch_url))
        fetch_urls[fetch_url] = None

    if not jobs:
        return markdown

    proxy_url = proxy_url_from_env()
    sem = asyncio.Semaphore(8)
    urls = list(fetch_urls)
    async with httpx.AsyncClient(follow_redirects=True, proxy=proxy_url) as client:
        results = await asyncio.gather(*(fetch_as_data_uri(client, u, sem) for u in urls))
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


@beartype
def _build_frontmatter(
    metadata: PostMetadata, freedium_url: str = "", source_url: str = ""
) -> str:
    """YAML frontmatter with title, subtitle, tags, and source links.

    Serialized with PyYAML (safe_dump) so arbitrary text — quotes, colons,
    newlines, unicode — is escaped correctly. Empty fields are skipped so
    consumers don't see `subtitle: ""` for articles that don't have one.
    """
    data: dict[str, object] = {}
    if metadata.title:
        data["title"] = metadata.title
    if metadata.subtitle:
        data["subtitle"] = metadata.subtitle
    tags = [t for t in metadata.tags if t]
    if tags:
        data["tags"] = tags
    if freedium_url:
        data["freedium_url"] = freedium_url
    if source_url:
        data["source_url"] = source_url
    if not data:
        return "---\n---\n"
    dumped = yaml.safe_dump(
        data,
        sort_keys=False,  # preserve title → subtitle → tags → links order
        allow_unicode=True,  # keep ’ é … literal instead of \uXXXX escapes
        default_flow_style=False,
        width=1_000_000,  # never line-wrap long scalars (URLs, subtitles)
    )
    return f"---\n{dumped}---\n"


def _build_heading(metadata: PostMetadata) -> str:
    """Title as an H1 + subtitle (italic) at the top of the document body, so
    the rendered .md shows them — not only in the frontmatter."""
    lines: list[str] = []
    if metadata.title:
        lines.append(f"# {metadata.title}")
    if metadata.subtitle:
        lines.append("")
        lines.append(f"*{metadata.subtitle}*")
    return "\n".join(lines) + "\n\n" if lines else ""


class MarkdownExportService:
    """Render → inline-images → resolve-gists → assemble a self-contained .md."""

    def __init__(
        self,
        medium_service: MediumService,
        public_url: str,
        gist_mode: ResolverMode = "raw",
    ):
        self._medium = medium_service
        self._public_url = public_url.rstrip("/")
        self._gist_mode = gist_mode

    async def to_markdown(self, url: str) -> ExportDocument:
        markdown, metadata = await self._medium.arender_with_metadata(url)
        markdown = await _inline_images_as_base64_markdown(markdown)
        resolved = await resolve_gists_in_markdown(markdown, mode=self._gist_mode)
        source_url = metadata.medium_url or url
        freedium_link = f"{self._public_url}/{source_url}"
        body = (
            _build_frontmatter(metadata, freedium_url=freedium_link, source_url=source_url)
            + "\n"
            + _build_heading(metadata)
            + resolved
        )
        return ExportDocument(
            content=body,
            filename=f"{_slugify(metadata.title)}.md",
            media_type="text/markdown; charset=utf-8",
        )
