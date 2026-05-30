"""Content-addressed cache for Medium CDN image bytes.

Unlike AsyncMongoDBCacheBackend (which zstd-compresses text), this stores
raw image bytes — JPEG/PNG/WebP are already compressed. Keyed by
"{width}:{image_id}".
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from bson.binary import Binary
from motor.motor_asyncio import AsyncIOMotorClient


class ImageCacheBackend:
    def __init__(
        self,
        connection_string: str,
        database: str = "freedium_cache",
        collection: str = "image_cache",
    ) -> None:
        self._client = AsyncIOMotorClient(connection_string)
        self._col = self._client[database][collection]

    async def aget(self, key: str) -> Optional[tuple[bytes, str]]:
        doc = await self._col.find_one({"_id": key})
        if doc is None:
            return None
        return bytes(doc["data"]), doc.get("content_type", "image/jpeg")

    async def aput(self, key: str, data: bytes, content_type: str) -> None:
        await self._col.update_one(
            {"_id": key},
            {
                "$set": {
                    "data": Binary(data),
                    "content_type": content_type,
                    "updated_at": _dt.datetime.utcnow(),
                },
                "$setOnInsert": {"created_at": _dt.datetime.utcnow()},
            },
            upsert=True,
        )

    async def aclose(self) -> None:
        self._client.close()
