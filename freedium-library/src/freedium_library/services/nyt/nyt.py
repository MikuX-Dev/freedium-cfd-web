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

        # Cover image goes in frontmatter (preview_image) → rendered as the
        # article header by the frontend, same as Medium. Body images are in
        # body_md. The final sub rewrites every static01 URL (frontmatter +
        # body) → /img/nyt (proxied, no-referrer).
        markdown = self._frontmatter(raw, url) + body_md
        return _STATIC01_RE.sub("/img/nyt/", markdown)

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

    @staticmethod
    def _pick_renditions(crops: list[dict[str, Any]]) -> tuple[str, str]:
        """(display, zoom) URLs from NYT crop renditions. display = widest
        ≤1100px, zoom = widest ≤2048px. ('', '') when none."""
        rends = sorted(
            (
                (r.get("width") or 0, r.get("url") or "")
                for crop in crops or []
                for r in (crop.get("renditions") or [])
                if "static01.nyt.com" in (r.get("url") or "")
            ),
        )
        if not rends:
            return "", ""
        disp = next((u for w, u in reversed(rends) if w <= 1100), rends[0][1])
        zoom = next((u for w, u in reversed(rends) if w <= 2048), rends[-1][1])
        return disp, zoom

    @staticmethod
    def _esc(text: str) -> str:
        return (
            text.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;")
        )

    @classmethod
    def _image_block_md(cls, block: dict[str, Any]) -> str:
        media = block.get("media") or {}
        if media.get("__typename") != "Image":
            return ""
        disp, zoom = cls._pick_renditions(media.get("crops") or [])
        if not disp:
            return ""
        cap = (media.get("caption") or {}).get("text") or ""
        credit = media.get("credit") or ""
        visible = " — ".join(p for p in (cap, credit) if p)
        # Match Medium's body-image structure: <img> with data-zoom-src +
        # data-caption (lightbox) inside a <figure> with a visible <figcaption>.
        # Raw HTML block (blank lines so the markdown pipeline treats it as HTML).
        cap_attr = f' data-caption="{cls._esc(visible)}"' if visible else ""
        figcap = f"<figcaption>{cls._esc(visible)}</figcaption>" if visible else ""
        return (
            f'\n<figure><img src="{cls._esc(disp)}" alt="{cls._esc(cap or "image")}"'
            f' loading="lazy" data-zoom-src="{cls._esc(zoom or disp)}"{cap_attr}'
            f' class="prose-image"/>{figcap}</figure>\n'
        )

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

    @classmethod
    def _frontmatter(cls, raw: dict[str, Any], url: str) -> str:
        import yaml

        headline = raw.get("headline")
        title = (
            headline.get("default")
            if isinstance(headline, dict)
            else (headline or "Untitled")
        )
        # bylines[].creators[] = Person {displayName, description (bio),
        # promotionalMedia (headshot)}. Build a multi-author list with images.
        authors: list[dict[str, str]] = []
        for b in raw.get("bylines") or []:
            for p in (b or {}).get("creators") or []:
                if p.get("__typename") != "Person":
                    continue
                name = p.get("displayName") or ""
                if not name:
                    continue
                entry: dict[str, str] = {"name": name}
                avatar, _z = cls._pick_renditions(
                    (p.get("promotionalMedia") or {}).get("crops") or []
                )
                if avatar:
                    entry["avatar"] = avatar
                if p.get("description"):
                    entry["bio"] = p["description"]
                authors.append(entry)
        if not authors:  # fallback to the rendered byline string
            rep = ""
            for b in raw.get("bylines") or []:
                rep = (b or {}).get("renderedRepresentation", "") or rep
            authors = [{"name": re.sub(r"^By\s+", "", rep).strip() or "The New York Times"}]

        section = raw.get("section") or {}
        date = raw.get("firstPublishedAt") or raw.get("lastMajorModification") or ""

        meta: dict[str, Any] = {
            "title": title,
            "author": {"name": ", ".join(a["name"] for a in authors)},
            "authors": authors,
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

        # Cover image → preview_image{medium,zoom,caption} (frontend renders the
        # article-header cover from this, same as Medium). static01 URLs are
        # rewritten to /img/nyt by the caller's final sub.
        pm = raw.get("promotionalMedia") or {}
        if pm.get("__typename") == "Image":
            disp, zoom = cls._pick_renditions(pm.get("crops") or [])
            if disp:
                meta["preview_image"] = {
                    "medium": disp,
                    "zoom": zoom or disp,
                    "caption": (pm.get("caption") or {}).get("text") or "",
                }

        return "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n\n"

    # ── unused abstractmethods ────────────────────────────────────────────────
    def _render(self, path: str) -> str:
        raise NotImplementedError("use async _arender")

    async def _asearch(self, keywords: list[str]) -> list[dict[str, str]]:
        return []

    def _search(self, keywords: list[str]) -> list[dict[str, str]]:
        return []
