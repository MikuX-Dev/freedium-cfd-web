"""Concurrent image pre-fetch + base64 inline for WeasyPrint input HTML.

WeasyPrint will fetch remote images serially and one slow URL stalls the
whole render. We download every <img src> URL up front in parallel,
encode as data: URI, and rewrite the HTML so WeasyPrint does zero
network I/O at render time.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
from typing import Final

import httpx
from loguru import logger
from lxml import html as lxml_html

_TIMEOUT: Final = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)
_MAX_IMAGE_BYTES: Final = 5_000_000
_MAX_PARALLEL: Final = 16

# Article HTML now emits relative /img/{width}/{id} URLs (our cached proxy)
# instead of direct miro.medium.com links. WeasyPrint can't resolve a
# relative URL, so map it back to the upstream miro CDN URL for fetching.
_IMG_PROXY_RE: Final = re.compile(r"^/img/(\d+)/(.+)$")


def _fetch_url_for_src(src: str) -> str | None:
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

# 1x1 transparent SVG for failed/oversize fetches.
_PLACEHOLDER_DATA_URI: Final = (
    "data:image/svg+xml;base64,"
    + base64.b64encode(
        b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'
    ).decode("ascii")
)


async def _fetch_one(
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


async def inline_images(html_str: str) -> str:
    """Walk the HTML, replace every remote img src with a data: URI.

    Failures (404, timeout, oversize, parse error) become a 1x1 SVG placeholder
    rather than raising — a missing image must not break the entire PDF.
    """
    if not html_str:
        return html_str
    tree = lxml_html.fragment_fromstring(html_str, create_parent="div")  # type: ignore[arg-type]

    # Map each inlinable <img src> to the absolute URL we must fetch.
    # Legacy miro URLs fetch as-is; new /img/{w}/{id} proxy URLs are
    # reconstructed into their upstream miro CDN equivalent.
    src_to_fetch: dict[str, str] = {}
    for img in tree.iter("img"):
        src = img.get("src")
        if not src or src in src_to_fetch:
            continue
        fetch_url = _fetch_url_for_src(src)
        if fetch_url is not None:
            src_to_fetch[src] = fetch_url

    if not src_to_fetch:
        return html_str

    fetch_urls = list(set(src_to_fetch.values()))

    # Route reconstructed miro fetches through the same Warp/HAProxy chain the
    # backend uses (so miro.medium.com sees a Cloudflare IP). Direct when unset.
    proxy_url = os.environ.get("PROXY_LIST", "").split(",")[0].strip() or None

    sem = asyncio.Semaphore(_MAX_PARALLEL)
    async with httpx.AsyncClient(follow_redirects=True, proxy=proxy_url) as client:
        results = await asyncio.gather(
            *(_fetch_one(client, u, sem) for u in fetch_urls)
        )
    fetch_to_data = dict(zip(fetch_urls, results))

    for img in tree.iter("img"):
        src = img.get("src")
        if src in src_to_fetch:
            img.set("src", fetch_to_data[src_to_fetch[src]])

    # fragment_fromstring wrapped us in a <div>; serialize children only.
    parts: list[str] = [
        lxml_html.tostring(child, encoding="unicode")  # type: ignore[assignment]
        for child in tree
    ]
    return (tree.text or "") + "".join(parts)
