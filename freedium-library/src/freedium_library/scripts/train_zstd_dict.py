"""Train a zstd dictionary from cached posts and write it to disk.

The dictionary is loaded at backend startup by AsyncMongoDBCacheBackend
to give roughly 2-3x better compression on similarly-shaped Medium
GraphQL responses vs. plain zstd.

Usage:
    MONGO_URL=mongodb://localhost:27017 \\
    python -m freedium_library.scripts.train_zstd_dict

Optional env:
    MONGO_DB         (default: freedium_cache)
    MONGO_COLLECTION (default: post_cache)
    SAMPLE_LIMIT     (default: 10000) — max docs to use as training samples
    DICT_SIZE        (default: 65536) — target dictionary size in bytes
    DICT_OUT_PATH    (default: bundled dict_v1.zstd) — override for testing

Exit codes:
    0 - dictionary written
    1 - configuration error
    2 - too few samples (< 100) to train usefully
    3 - source DB error
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import zstandard as zstd
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient

from freedium_library.utils.cache.db.mongo import (
    _DICT_FILENAME,
    _decompressor_plain,
)


MIN_SAMPLES = 100


def _require(env: str) -> str:
    val = os.environ.get(env)
    if not val:
        logger.error(f"missing required env var: {env}")
        sys.exit(1)
    return val


def _default_dict_path() -> Path:
    """Path to the bundled dict_v1.zstd file inside the package."""
    here = Path(__file__).resolve().parent.parent
    return here / "utils" / "cache" / "db" / _DICT_FILENAME


async def _gather_samples(
    client: AsyncIOMotorClient, db: str, collection: str, limit: int
) -> list[bytes]:
    """Pull up to `limit` documents at random and return their decompressed
    JSON bytes — the training input for zstd.

    Samples are decompressed because we want the dictionary to learn the
    structure of the cleartext, not the structure of a previous dictionary's
    output."""
    col = client[db][collection]
    cursor = col.aggregate([{"$sample": {"size": limit}}])
    samples: list[bytes] = []
    async for doc in cursor:
        compression = doc.get("compression", "zstd")
        blob = doc["value"]
        try:
            if compression == "zstd":
                raw = _decompressor_plain.decompress(blob)
            elif compression == "zstd_dict_v1":
                # Self-referential case: we're training the dict that this
                # doc was compressed with. Skip — we don't have the dict yet.
                continue
            else:
                logger.warning(
                    f"skipping doc with unknown compression {compression!r}"
                )
                continue
        except zstd.ZstdError as exc:
            logger.warning(f"skipping unreadable doc: {exc}")
            continue
        samples.append(raw)
    return samples


async def _run() -> int:
    mongo_url = _require("MONGO_URL")
    mongo_db = os.environ.get("MONGO_DB", "freedium_cache")
    mongo_collection = os.environ.get("MONGO_COLLECTION", "post_cache")
    sample_limit = int(os.environ.get("SAMPLE_LIMIT", "10000"))
    dict_size = int(os.environ.get("DICT_SIZE", "65536"))
    out_path = Path(os.environ.get("DICT_OUT_PATH", "") or _default_dict_path())

    logger.info(
        f"training zstd dictionary from {mongo_db}.{mongo_collection} "
        f"(sample_limit={sample_limit}, dict_size={dict_size}, out={out_path})"
    )

    client = AsyncIOMotorClient(mongo_url)
    try:
        samples = await _gather_samples(
            client, mongo_db, mongo_collection, sample_limit
        )
    except Exception as exc:
        logger.exception(f"failed to read samples from Mongo: {exc}")
        return 3
    finally:
        client.close()

    if len(samples) < MIN_SAMPLES:
        logger.error(
            f"only {len(samples)} usable samples found, need at least "
            f"{MIN_SAMPLES}. Populate the cache first."
        )
        return 2

    logger.info(
        f"training on {len(samples)} samples "
        f"({sum(len(s) for s in samples) / (1024 * 1024):.1f} MiB total)"
    )
    dict_data = zstd.train_dictionary(dict_size, samples)
    dict_bytes = dict_data.as_bytes()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(dict_bytes)

    logger.info(
        f"dictionary written: {len(dict_bytes)} bytes "
        f"({len(dict_bytes) / 1024:.1f} KiB) -> {out_path}"
    )
    logger.info(
        "RESTART the backend so the new dictionary is loaded. "
        "Existing cache entries remain decompressible (tagged 'zstd') "
        "and will be re-cached under the new dict tag on next render."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
