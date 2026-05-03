"""Concurrent image pre-fetch + base64 inline for WeasyPrint input HTML.

WeasyPrint will fetch remote images serially and one slow URL stalls the
whole render. We download every <img src> / <source srcset> URL up front
in parallel, encode as data: URI, and rewrite the HTML so WeasyPrint does
zero network I/O at render time.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Final

import httpx
from loguru import logger
from lxml import html as lxml_html

_TIMEOUT: Final = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)
_MAX_IMAGE_BYTES: Final = 5_000_000
_MAX_PARALLEL: Final = 16

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

    urls: set[str] = set()
    for img in tree.iter("img"):
        src = img.get("src")
        if src and src.startswith(("http://", "https://")):
            urls.add(src)

    if not urls:
        return html_str

    sem = asyncio.Semaphore(_MAX_PARALLEL)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(
            *(_fetch_one(client, u, sem) for u in urls)
        )
    mapping = dict(zip(urls, results))

    for img in tree.iter("img"):
        src = img.get("src")
        if src in mapping:
            img.set("src", mapping[src])

    # fragment_fromstring wrapped us in a <div>; serialize children only.
    parts: list[str] = [
        lxml_html.tostring(child, encoding="unicode")  # type: ignore[assignment]
        for child in tree
    ]
    return "".join(parts) + (tree.text or "")
