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

import httpx
from loguru import logger

from freedium_library.services.base import BaseService
from freedium_library.services.nyt import client as nyt_client


# Standard NYT article URL: nytimes.com/YYYY/MM/DD/<section>/<slug>.html
# Excludes /live/ and /interactive/ (different DOM → handled as unsupported).
_NYT_ARTICLE_RE = re.compile(
    r"^https?://(www\.)?nytimes\.com/\d{4}/\d{2}/\d{2}/(?!interactive/|live/)[^?#]+",
    re.IGNORECASE,
)
_STATIC01_RE = re.compile(r"https?://static01\.nyt\.com/", re.IGNORECASE)

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
        return bool(_NYT_ARTICLE_RE.match(path.strip()))

    async def _ais_valid(self, path: str) -> bool:
        return self._is_valid(path)

    # ── render ──────────────────────────────────────────────────────────────
    async def _arender(self, path: str) -> str:
        """Fetch + convert to markdown WITH frontmatter (the frontend contract).

        arender_with_frontmatter() defaults to this, which is what the render
        handler calls for non-medium services."""
        url = path.strip()
        # Blocking client (curl_cffi) — run in a thread so it never stalls the
        # event loop. article_raw carries headline/bylines/date + the body HTML.
        import asyncio

        raw = await asyncio.to_thread(self._client.article_raw, url)
        if not raw:
            raise NytUnsupportedError("empty NYT response")
        typename = raw.get("__typename")
        if typename not in _RENDERABLE_TYPES:
            raise NytUnsupportedError(f"unsupported NYT type: {typename}")

        html = (raw.get("hybridBody") or {}).get("main", {}).get("contents") or ""
        if len(html) < 500:
            raise NytUnsupportedError("no article body in NYT response")

        markdown = await self._html_to_markdown(html)
        if len(markdown) < 200:
            raise NytUnsupportedError("article body did not convert")

        # Proxy NYT CDN images through /img (no-referrer, same as Medium).
        markdown = _STATIC01_RE.sub("/img/nyt/", markdown)

        return self._frontmatter(raw, url) + markdown

    async def _html_to_markdown(self, html: str) -> str:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(
                self._mdream_url + "/",
                content=html.encode("utf-8"),
                headers={"content-type": "text/html"},
            )
            resp.raise_for_status()
            return resp.text

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
