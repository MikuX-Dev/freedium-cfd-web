"""Public, read-only image proxy: GET /img/{width}/{image_id}.

Serves Medium CDN images from a Mongo cache. On a miss, fetches from
miro.medium.com through the WARP proxy (PROXY_LIST), stores, and returns.
SSRF-safe: the upstream host is hardcoded; width is allowlisted; image_id
is regex-validated. Browser never contacts Medium.
"""
from __future__ import annotations

import os
import re

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from loguru import logger

from freedium_library.utils.cache.db.image_cache import ImageCacheBackend

# Widths we actually emit (feed covers 800/1400; article body 700/2000/4000).
_ALLOWED_WIDTHS = {700, 800, 1400, 2000, 4000}
# Medium image ids: alphanumeric, '*', '.', '-', '_'. Never a slash/scheme.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._*-]{0,200}$")
_MAX_BYTES = 15 * 1024 * 1024  # don't cache images larger than ~15MB
_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}

_backend: ImageCacheBackend | None = None


def _get_backend() -> ImageCacheBackend:
    global _backend
    if _backend is None:
        _backend = ImageCacheBackend(
            connection_string=os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
            database=os.environ.get("MONGO_DB", "freedium_cache"),
        )
    return _backend


def _proxy() -> str | None:
    first = os.environ.get("PROXY_LIST", "").split(",")[0].strip()
    return first or None


def register_images_router(app: FastAPI) -> None:
    @app.get("/img/{width}/{image_id}", include_in_schema=False)
    async def get_image(width: int, image_id: str) -> Response:
        if width not in _ALLOWED_WIDTHS:
            raise HTTPException(status_code=400, detail="unsupported width")
        if not _ID_RE.match(image_id):
            raise HTTPException(status_code=400, detail="invalid image id")

        key = f"{width}:{image_id}"
        backend = _get_backend()

        try:
            cached = await backend.aget(key)
        except Exception as exc:  # cache read failure → treat as miss
            logger.warning(f"image_cache read failed for {key}: {exc!r}")
            cached = None

        if cached is not None:
            data, content_type = cached
            return Response(content=data, media_type=content_type, headers=_CACHE_HEADERS)

        # Miss → fetch from Medium CDN (host hardcoded; via WARP if configured)
        upstream = f"https://miro.medium.com/v2/resize:fit:{width}/{image_id}"
        try:
            async with httpx.AsyncClient(
                proxy=_proxy(),
                timeout=25.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/146 Safari/537.36"},
            ) as client:
                resp = await client.get(upstream)
        except Exception as exc:
            logger.warning(f"image fetch failed for {key}: {exc!r}")
            raise HTTPException(status_code=502, detail="upstream image fetch failed")

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code if resp.status_code in (404, 403) else 502, detail="upstream error")

        data = resp.content
        content_type = resp.headers.get("content-type", "image/jpeg")
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=502, detail="not an image")

        if len(data) <= _MAX_BYTES:
            try:
                await backend.aput(key, data, content_type)
            except Exception as exc:  # cache write failure must not break the response
                logger.warning(f"image_cache write failed for {key}: {exc!r}")

        return Response(content=data, media_type=content_type, headers=_CACHE_HEADERS)
