"""Financial Times article client via the unauthenticated mobile app API.

Endpoint: app-api.ft.com/__content/v6/article/{uuid}
Auth: None (no API key, no session required)
TLS: CurlRequest (chrome146) bypasses Cloudflare.

Discovered via mitmproxy interception of com.ft.news (FT Android v2.296.0).
"""
from __future__ import annotations

import re
from typing import Any

from freedium_library.utils.http import CurlRequest

APP_API_URL = "https://app-api.ft.com/__content/v6/article/{uuid}?useVanities=false"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def extract_uuid(url: str) -> str:
    m = UUID_RE.search(url)
    if not m:
        raise ValueError(f"No UUID in URL: {url}")
    return m.group(0)


async def fetch_article(request: CurlRequest, url: str) -> dict[str, Any]:
    """Fetch the full FT article via the mobile app API."""
    uuid = extract_uuid(url)
    resp = await request.aget(APP_API_URL.format(uuid=uuid))
    resp.raise_for_status()
    data = resp.json()
    article = data.get("data", {}).get("content")
    if not article:
        raise ValueError("Unexpected FT API response structure")
    return article
