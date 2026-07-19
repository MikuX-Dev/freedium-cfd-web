"""Reuters article client — appends ?outputType=json to any Reuters URL.

Returns the full article JSON including premium/metered content without
any paywall enforcement. No auth, no signing.
"""
from __future__ import annotations

import httpx

HEADERS = {
    "User-Agent": (
        "ReutersNews/7.42.0.1783014837 "
        "Mozilla/5.0 (Linux; Android 13; Pixel 7 Build/TQ3A.230901.001; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json",
}


async def fetch_article(url: str, timeout: int = 20) -> list:
    """Fetch the full article JSON blocks."""
    fetch_url = url.rstrip("/") + "/?outputType=json" if "?" not in url else url + "&outputType=json"
    async with httpx.AsyncClient() as client:
        resp = await client.get(fetch_url, headers=HEADERS, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()
