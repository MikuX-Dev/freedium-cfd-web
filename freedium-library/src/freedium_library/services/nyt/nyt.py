"""NytService — renders New York Times articles for Freedium.

Pipeline (all validated):
  public NYT url
    → nyt_client.article_raw(url, proxy=WARP)   # samizdat APQ GraphQL, full content
    → hybridBody.main.contents (full ~500KB HTML)
    → POST to mdream-svc                          # isolates body → clean markdown
    → prepend YAML frontmatter (same schema as MediumService)
    → rewrite static01.nyt.com image URLs → /img/nyt/…  (proxied, no-referrer)

Content is always full (NYT paywall is client-side). Egress via WARP — NYT's
API is geo-locked (US/EU), and WARP exits an allowed region. Requires
NYT_SIGNING_KEY in env (the RSA signing key); without it the service is inert.
"""
from __future__ import annotations

import re
from typing import Any

# import httpx  # only needed for the (disabled) mdream HTML→markdown fallback
from loguru import logger

from freedium_library.services.base import BaseService
from freedium_library.services.nyt import client as nyt_client


# Any nytimes.com subdomain (www, cooking, …). Content paths: dated articles
# (/YYYY/MM/DD/…), cooking (/article/, /recipes/), wirecutter. Excludes
# non-article surfaces (interactive/live/section/video/games) — those fall
# through to "unsupported" via the __typename gate anyway.
_NYT_ARTICLE_RE = re.compile(
    r"^https?://([a-z0-9-]+\.)*nytimes\.com/"
    r"(?!interactive/|live/|section/|column/|by/|video/|spotlight/|games/|crosswords?/)"
    r"(\d{4}/\d{2}/\d{2}/|article/|recipes?/|wirecutter/)[^?#]+",
    re.IGNORECASE,
)
_STATIC01_RE = re.compile(r"https?://static01\.nyt\.com/", re.IGNORECASE)
# Proxies/SvelteKit collapse the `//` in /https://nytimes.com/… → `https:/…`.
# Medium's extractor tolerates it; restore it before matching/fetching.
_COLLAPSED_SCHEME_RE = re.compile(r"^(https?):/+", re.IGNORECASE)


def _normalize_url(path: str) -> str:
    return _COLLAPSED_SCHEME_RE.sub(r"\1://", path.strip())

# Article __typename values we can render. Others (Video, EmbeddedInteractive)
# don't have a readable hybridBody → unsupported.
_RENDERABLE_TYPES = {"Article", "AthleticArticle"}


class NytUnsupportedError(Exception):
    """Raised for NYT content we can't render (video, interactive, etc.)."""


class NytService(BaseService):
    """Renders nytimes.com articles via the reverse-engineered mobile API."""

    def __init__(
        self,
        proxy: str | None = None,
        mdream_url: str = "http://mdream:8085",
    ) -> None:
        self._proxy = proxy
        self._mdream_url = mdream_url.rstrip("/")
        # No NYT-S cookie: article content is public (paywall is client-side).
        # One client instance (rotates device metadata per request internally).
        self._client = nyt_client.NYTClient(proxy=proxy, rotate_devices=True)

    # ── validation ──────────────────────────────────────────────────────────
    def _is_valid(self, path: str) -> bool:
        return bool(_NYT_ARTICLE_RE.match(_normalize_url(path)))

    async def _ais_valid(self, path: str) -> bool:
        return self._is_valid(path)

    # ── render ──────────────────────────────────────────────────────────────
    async def _arender(self, path: str) -> str:
        """Fetch + convert to markdown WITH frontmatter (the frontend contract).

        arender_with_frontmatter() defaults to this, which is what the render
        handler calls for non-medium services."""
        url = _normalize_url(path)
        # Blocking client (curl_cffi) — run in a thread so it never stalls the
        # loop. article_structured returns TYPED body blocks (paragraphs,
        # headings, ImageBlocks with full crop URLs) — so inline images resolve
        # server-side (the hybridBody HTML lazy-loads them with no URLs).
        import asyncio

        raw = await asyncio.to_thread(self._client.article_structured, url)
        if not raw:
            raise NytUnsupportedError("empty NYT response")
        typename = raw.get("__typename")
        if typename not in _RENDERABLE_TYPES:
            raise NytUnsupportedError(f"unsupported NYT type: {typename}")

        blocks = ((raw.get("body") or {}).get("content")) or []
        body_md = self._blocks_to_markdown(blocks)
        if len(body_md) < 50:
            raise NytUnsupportedError("no renderable body blocks")

        # Lead (cover) image from promotionalMedia + the inline body markdown.
        markdown = self._lead_image_md(raw) + body_md

        # Proxy NYT CDN images through /img (no-referrer, same as Medium).
        markdown = _STATIC01_RE.sub("/img/nyt/", markdown)

        return self._frontmatter(raw, url) + markdown

    @classmethod
    def _blocks_to_markdown(cls, blocks: list[dict[str, Any]]) -> str:
        """Render NYT typed body blocks → markdown. Unknown blocks are skipped."""
        out: list[str] = []
        for b in blocks:
            t = b.get("__typename")
            if t == "ParagraphBlock":
                text = cls._inline_md(b.get("content") or [])
                if text.strip():
                    out.append(text)
            elif t == "Heading2Block":
                text = cls._inline_md(b.get("content") or [])
                if text.strip():
                    out.append(f"## {text}")
            elif t == "ImageBlock":
                img = cls._image_block_md(b)
                if img:
                    out.append(img)
            # HeaderBasicBlock (headline/byline → frontmatter), InteractiveBlock,
            # unknown → skipped.
        return "\n\n".join(out)

    @staticmethod
    def _inline_md(inlines: list[dict[str, Any]]) -> str:
        """Concatenate TextInline runs, applying link/bold/italic formats."""
        parts: list[str] = []
        for node in inlines:
            if node.get("__typename") == "LineBreakInline":
                parts.append("\n")
                continue
            text = node.get("text")
            if not text:
                continue
            href = None
            bold = italic = False
            for fmt in node.get("formats") or []:
                ft = fmt.get("__typename") or ""
                if ft == "LinkFormat":
                    href = fmt.get("url")
                elif "Bold" in ft or "Strong" in ft:
                    bold = True
                elif "Italic" in ft or "Emphasis" in ft:
                    italic = True
            if bold:
                text = f"**{text}**"
            if italic:
                text = f"_{text}_"
            if href:
                text = f"[{text}]({href})"
            parts.append(text)
        return "".join(parts)

    @classmethod
    def _image_block_md(cls, block: dict[str, Any]) -> str:
        media = block.get("media") or {}
        if media.get("__typename") != "Image":
            return ""
        best_w, best_url = 0, ""
        for crop in media.get("crops") or []:
            for r in crop.get("renditions") or []:
                u, w = r.get("url") or "", r.get("width") or 0
                if "static01.nyt.com" in u and best_w < w <= 2048:
                    best_w, best_url = w, u
        if not best_url:
            return ""
        cap = (media.get("caption") or {}).get("text") or ""
        credit = media.get("credit") or ""
        alt = cap or "image"
        md = f"![{alt}]({best_url})"
        tail = " — ".join(p for p in (cap, credit) if p)
        return f"{md}\n\n*{tail}*" if tail else md

    @staticmethod
    def _lead_image_md(raw: dict[str, Any]) -> str:
        """Markdown for the article's lead image from promotionalMedia crops
        (the body figures are lazy-loaded and unrecoverable). Picks the widest
        rendition up to 2048px. Empty string when there's no usable image."""
        pm = raw.get("promotionalMedia") or {}
        if pm.get("__typename") != "Image":
            return ""
        best_w, best_url = 0, ""
        for crop in pm.get("crops") or []:
            for r in crop.get("renditions") or []:
                url = r.get("url") or ""
                w = r.get("width") or 0
                if "static01.nyt.com" in url and best_w < w <= 2048:
                    best_w, best_url = w, url
        if not best_url:
            return ""
        caption = ""
        cap = pm.get("caption")
        if isinstance(cap, dict):
            caption = cap.get("text") or ""
        return f"![{caption}]({best_url})\n\n"

    # Legacy path: convert hybridBody HTML → markdown via the mdream sidecar.
    # Superseded by the structured-body renderer (which recovers inline image
    # URLs the lazy HTML lacks). Kept (disabled) as a fallback option.
    # async def _html_to_markdown(self, html: str) -> str:
    #     import httpx
    #     async with httpx.AsyncClient(timeout=30) as c:
    #         resp = await c.post(
    #             self._mdream_url + "/",
    #             content=html.encode("utf-8"),
    #             headers={"content-type": "text/html"},
    #         )
    #         resp.raise_for_status()
    #         return resp.text

    @staticmethod
    def _frontmatter(raw: dict[str, Any], url: str) -> str:
        import yaml

        headline = raw.get("headline")
        title = (
            headline.get("default")
            if isinstance(headline, dict)
            else (headline or "Untitled")
        )
        # bylines: [{"renderedRepresentation": "By Tyler Pager"}]
        names = []
        for b in raw.get("bylines") or []:
            rep = (b or {}).get("renderedRepresentation", "")
            if rep:
                names.append(re.sub(r"^By\s+", "", rep).strip())
        author_name = ", ".join(names) or "The New York Times"

        section = raw.get("section") or {}
        date = raw.get("firstPublishedAt") or raw.get("lastMajorModification") or ""

        meta: dict[str, Any] = {
            "title": title,
            "author": {"name": author_name},
            "publication": "The New York Times",
            "is_locked": False,
            "url": url,
        }
        if raw.get("summary"):
            meta["subtitle"] = raw["summary"]
        if date:
            meta["date"] = date
        if isinstance(section, dict) and section.get("displayName"):
            meta["tags"] = [section["displayName"]]

        return "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n\n"

    # ── unused abstractmethods ────────────────────────────────────────────────
    def _render(self, path: str) -> str:
        raise NotImplementedError("use async _arender")

    async def _asearch(self, keywords: list[str]) -> list[dict[str, str]]:
        return []

    def _search(self, keywords: list[str]) -> list[dict[str, str]]:
        return []
