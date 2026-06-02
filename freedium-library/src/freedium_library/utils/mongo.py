"""Shared async Mongo access.

One process-wide motor client + a collection helper, so call sites don't each
spin up their own AsyncIOMotorClient and re-read the MONGO_URL / MONGO_DB env.
A single client means a single connection pool per process.

Note: this is for the ad-hoc, non-DI call sites (the /img count, the denylist,
the article-count task). The cache backends in utils/cache/db/ are
DI-parameterized and intentionally manage their own clients.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

_client: "AsyncIOMotorClient | None" = None


def _get_client() -> "AsyncIOMotorClient":
    global _client
    if _client is None:
        from motor.motor_asyncio import AsyncIOMotorClient

        _client = AsyncIOMotorClient(
            os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        )
    return _client


def get_collection(name: str) -> "AsyncIOMotorCollection":
    """Return the named collection in the configured DB (MONGO_DB env,
    default 'freedium_cache'), backed by the shared process-wide client."""
    db = os.environ.get("MONGO_DB", "freedium_cache")
    return _get_client()[db][name]
