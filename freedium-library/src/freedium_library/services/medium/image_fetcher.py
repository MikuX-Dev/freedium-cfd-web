"""Shared image-fetch primitives: resolve <img src> → absolute URL, fetch and
base64-encode as a data: URI.

Used by both the PDF image inliner (WeasyPrint pre-fetch) and the markdown
export (self-contained .md). Kept dependency-light (httpx, base64, asyncio,
re, os, loguru) so either caller can import it without pulling in lxml.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
from typing import Final

import httpx
from loguru import logger

_TIMEOUT: Final = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)
_MAX_IMAGE_BYTES: Final = 5_000_000
_MAX_PARALLEL: Final = 16

# Article HTML now emits relative /img/{width}/{id} URLs (our cached proxy)
# instead of direct miro.medium.com links. WeasyPrint can't resolve a
# relative URL, so map it back to the upstream miro CDN URL for fetching.
_IMG_PROXY_RE: Final = re.compile(r"^/img/(\d+)/(.+)$")

# 1x1 transparent SVG for failed/oversize fetches.
_PLACEHOLDER_DATA_URI: Final = (
    "data:image/svg+xml;base64,"
    + base64.b64encode(
        b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'
    ).decode("ascii")
)


def proxy_url_from_env() -> str | None:
    """Return the first proxy URL from PROXY_LIST, or None when unset.

    Route reconstructed miro fetches through the same Warp/HAProxy chain the
    backend uses (so miro.medium.com sees a Cloudflare IP). Direct when unset.
    """
    return os.environ.get("PROXY_LIST", "").split(",")[0].strip() or None


def fetch_url_for_src(src: str) -> str | None:
    """Return an absolute URL to fetch for a given <img src>, or None to skip.

    Handles both the legacy direct miro URLs and the new relative
    /img/{width}/{id} proxy form (reconstructed into the equivalent
    miro.medium.com resize URL).
    """
    if src.startswith(("http://", "https://")):
        return src
    m = _IMG_PROXY_RE.match(src)
    if m:
        width, image_id = m.group(1), m.group(2)
        return f"https://miro.medium.com/v2/resize:fit:{width}/{image_id}"
    return None


async def fetch_as_data_uri(
    client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore
) -> str:
    """Fetch a single image and return a data: URI, or the placeholder on failure."""
    async with sem:
        try:
            resp = await client.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            content = resp.content
            if len(content) > _MAX_IMAGE_BYTES:
                logger.warning(
                    f"image_inliner: {url} exceeded {_MAX_IMAGE_BYTES}B, using placeholder"
                )
                return _PLACEHOLDER_DATA_URI
            content_type = resp.headers.get("content-type", "image/png").split(";")[0].strip()
            b64 = base64.b64encode(content).decode("ascii")
            return f"data:{content_type};base64,{b64}"
        except Exception as exc:  # noqa: BLE001 — placeholder on any failure
            logger.warning(f"image_inliner: {url} failed ({exc!r}), using placeholder")
            return _PLACEHOLDER_DATA_URI
