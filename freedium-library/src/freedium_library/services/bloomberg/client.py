"""Bloomberg mobile CDN API client.

Two-step fetch: urllookup resolves the URL → full story JSON (often with
components inline). If not, falls back to stories/{internalID}. No auth,
no signing, no geo-block.
"""
from __future__ import annotations

import httpx

URL_LOOKUP_API = "https://cdn-mobapi.bloomberg.com/wssmobile/v1/urllookup/find"
STORY_API = "https://cdn-mobapi.bloomberg.com/wssmobile/v1/stories"

HEADERS = {
    "user-agent": (
        "BloombergHorseshoe|Android|13|6.61.1.5530538.1d2bc00ede|"
        "1d2bc00eded06e5bb321a7fb53bb534b1c6d2798"
    ),
    "Accept-Encoding": "gzip",
}


async def fetch_article(url: str, timeout: int = 30) -> dict:
    """Resolve a bloomberg.com URL to a full story object."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            URL_LOOKUP_API,
            params={"variant": "android", "newsEdition": "UK", "liveRegion": "PAN_EUROPE", "url": url},
            headers=HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        if "components" in data:
            return data

        internal_id = data.get("resourceId") or data.get("internalID")
        if not internal_id:
            raise ValueError("Could not resolve Bloomberg article ID from URL.")

        resp2 = await client.get(
            f"{STORY_API}/{internal_id}",
            params={"contentCliff": "false"},
            headers=HEADERS,
            timeout=timeout,
        )
        resp2.raise_for_status()
        return resp2.json()
