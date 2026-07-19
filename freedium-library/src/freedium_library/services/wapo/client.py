"""Washington Post content API client.

Fetches full article JSON via the WaPo mobile app's internal Rainbow API,
which returns complete structured content without paywall checks. No auth,
no signing, no geo-block — just two headers (CLIENT-APP + User-Agent).

Discovered by analyzing the Android app's network traffic with mitmproxy.
"""
from __future__ import annotations

import httpx

CONTENT_API = (
    "https://rainbowapi-a.wpdigital.net/rainbow-data-service/rainbow/"
    "content-by-url.json"
)

HEADERS = {
    "CLIENT-APP": "android-classic",
    "User-Agent": (
        "Dalvik/2.1.0 (Linux; U; Android 13; Pixel 7 Build/TQ3A.230901.001) "
        "Classic/7.10.0 (2945)#2245 android/33 phone app-classic-android:google"
    ),
    "Accept-Encoding": "gzip",
}


async def fetch_article(url: str, timeout: int = 30) -> dict:
    """Fetch article JSON from the Rainbow content API (async)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            CONTENT_API,
            params={"url": url, "platform": "iphoneclassic", "followLinks": "false"},
            headers=HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
