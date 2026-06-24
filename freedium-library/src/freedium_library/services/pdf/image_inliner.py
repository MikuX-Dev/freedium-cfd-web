"""Concurrent image pre-fetch + base64 inline for WeasyPrint input HTML.

WeasyPrint will fetch remote images serially and one slow URL stalls the
whole render. We download every <img src> URL up front in parallel,
encode as data: URI, and rewrite the HTML so WeasyPrint does zero
network I/O at render time.
"""

from __future__ import annotations

import asyncio

import httpx
from lxml import html as lxml_html

from freedium_library.services.medium.image_fetcher import (
    _MAX_PARALLEL,
    fetch_as_data_uri,
    fetch_url_for_src,
    proxy_url_from_env,
)


async def inline_images(html_str: str) -> str:
    """Walk the HTML, replace every remote img src with a data: URI.

    Failures (404, timeout, oversize, parse error) become a 1x1 SVG placeholder
    rather than raising — a missing image must not break the entire PDF.
    """
    if not html_str:
        return html_str
    # A full document (<!doctype>/<html>) must be parsed as a document so the
    # <head>/<style> (incl. @page rules) survive — fragment_fromstring drops
    # everything outside <body>, which silently strips ALL the print CSS.
    is_full_doc = html_str.lstrip()[:60].lower().startswith(("<!doctype", "<html"))
    if is_full_doc:
        tree = lxml_html.document_fromstring(html_str)  # type: ignore[arg-type]
    else:
        tree = lxml_html.fragment_fromstring(html_str, create_parent="div")  # type: ignore[arg-type]

    # Map each inlinable <img src> to the absolute URL we must fetch.
    # Legacy miro URLs fetch as-is; new /img/{w}/{id} proxy URLs are
    # reconstructed into their upstream miro CDN equivalent.
    src_to_fetch: dict[str, str] = {}
    for img in tree.iter("img"):
        src = img.get("src")
        if not src or src in src_to_fetch:
            continue
        fetch_url = fetch_url_for_src(src)
        if fetch_url is not None:
            src_to_fetch[src] = fetch_url

    if not src_to_fetch:
        return html_str

    fetch_urls = list(set(src_to_fetch.values()))

    # Route reconstructed miro fetches through the same Warp/HAProxy chain the
    # backend uses (so miro.medium.com sees a Cloudflare IP). Direct when unset.
    proxy_url = proxy_url_from_env()

    sem = asyncio.Semaphore(_MAX_PARALLEL)
    async with httpx.AsyncClient(follow_redirects=True, proxy=proxy_url) as client:
        results = await asyncio.gather(
            *(fetch_as_data_uri(client, u, sem) for u in fetch_urls)
        )
    fetch_to_data = dict(zip(fetch_urls, results))

    for img in tree.iter("img"):
        src = img.get("src")
        if src in src_to_fetch:
            img.set("src", fetch_to_data[src_to_fetch[src]])

    if is_full_doc:
        # Serialize the whole document (<html> with <head>/<style>/@page intact).
        return lxml_html.tostring(  # type: ignore[return-value]
            tree, encoding="unicode", doctype="<!DOCTYPE html>"
        )
    # fragment_fromstring wrapped us in a <div>; serialize children only.
    parts: list[str] = [
        lxml_html.tostring(child, encoding="unicode")  # type: ignore[assignment]
        for child in tree
    ]
    return (tree.text or "") + "".join(parts)
