"""Scheduled task: convert cached PNG images to JPEG XL (JXL) every 2 min.

Batch-converts up to BATCH_SIZE unconverted PNGs per cycle. Stores the result
as content_type=image/jxl in the image_cache collection, so the /img/ endpoint
serves JXL natively to Chrome/Safari/Edge (~85%) and on-the-fly re-encodes to
JPEG for Firefox (via djxl, ~13ms).

Metrics:
  freedium_jxl_conversion_total{outcome}   — success | cjxl_timeout | cjxl_error | size_anomaly
  freedium_jxl_conversion_duration_seconds — histogram per image
Errors logged to stdout → Promtail → Loki.
"""
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger
from pymongo.errors import OperationFailure

from freedium_library.tasks import broker

BATCH_SIZE = int(os.getenv("JXL_BATCH_SIZE", "50"))
MAX_PARALLEL = int(os.getenv("JXL_PARALLEL", "4"))
MIN_BYTES = int(os.getenv("JXL_MIN_BYTES", "50000"))
CJXL_TIMEOUT = int(os.getenv("JXL_TIMEOUT", "30"))


def _col():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    )
    db = os.environ.get("MONGO_DB", "freedium_cache")
    return client[db]["image_cache"]


async def _convert_one(doc_id: str, png_bytes: bytes, sem: asyncio.Semaphore) -> bytes | None:
    """Run cjxl in a subprocess and return the JXL bytes, or None on failure."""
    async with sem:
        proc = await asyncio.create_subprocess_exec(
            "cjxl", "-", "-", "-d", "1", "-e", "9", "--num_threads=1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=png_bytes), timeout=CJXL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(f"cjxl timeout after {CJXL_TIMEOUT}s")
        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:300]
            raise RuntimeError(f"cjxl exit {proc.returncode}: {err}")
        jxl = stdout
        # Sanity check: JXL should be meaningfully smaller. If it's >2× the
        # PNG input, something went wrong (e.g. upscaling noise) — reject.
        if len(jxl) > len(png_bytes) * 2:
            return None  # caller records size_anomaly
        return jxl


@broker.task(schedule=[{"cron": "*/2 * * * *"}])
async def convert_pngs_to_jxl() -> None:
    from bson import Binary

    from freedium_library.api.metrics import (
        JXL_CONVERSION,
        JXL_CONVERSION_DURATION,
    )

    col = _col()
    # Idempotent: index content_type so the find scan is fast. Harmless on repeat.
    try:
        await col.create_index("content_type")
    except OperationFailure:
        pass

    docs = []
    # Use aggregation with $binarySize so Mongo filters by size server-side.
    # Exclude previously-seen anomalous PNGs (JXL > 2× input — already as
    # small as they'll get) so they don't waste a batch slot every cycle.
    async for doc in col.aggregate([
        {"$match": {"content_type": "image/png", "jxl_anomalous": {"$exists": False}}},
        {"$addFields": {"_size": {"$binarySize": "$data"}}},
        {"$match": {"_size": {"$gte": MIN_BYTES}}},
        {"$limit": BATCH_SIZE},
    ]):
        docs.append((doc["_id"], doc["data"]))

    if not docs:
        return

    sem = asyncio.Semaphore(MAX_PARALLEL)
    stats: dict[str, int] = {"ok": 0, "fail": 0, "anomaly": 0}

    async def _do(doc_id: str, png_bytes: bytes) -> None:
        t0 = time.monotonic()
        try:
            jxl = await _convert_one(doc_id, png_bytes, sem)
        except TimeoutError:
            stats["fail"] += 1
            JXL_CONVERSION.labels(outcome="cjxl_timeout").inc()
            logger.error(f"jxl conversion timeout for {doc_id}")
            return
        except Exception as exc:  # noqa: BLE001
            stats["fail"] += 1
            JXL_CONVERSION.labels(outcome="cjxl_error").inc()
            logger.error(f"jxl conversion failed for {doc_id}: {exc!r}")
            return
        JXL_CONVERSION_DURATION.observe(time.monotonic() - t0)

        if jxl is None:
            stats["anomaly"] += 1
            JXL_CONVERSION.labels(outcome="size_anomaly").inc()
            # Mark so the aggregation filter excludes it next cycle.
            await col.update_one({"_id": doc_id}, {"$set": {"jxl_anomalous": True}})
            return

        await col.update_one(
            {"_id": doc_id},
            {"$set": {"data": Binary(jxl), "content_type": "image/jxl"}},
        )
        stats["ok"] += 1
        JXL_CONVERSION.labels(outcome="success").inc()

    await asyncio.gather(*(_do(did, data) for did, data in docs))

    if stats["ok"] or stats["fail"]:
        logger.info(
            f"jxl converter: {stats['ok']} ok, {stats['fail']} failed, "
            f"{stats['anomaly']} anomalous of {len(docs)}"
        )
