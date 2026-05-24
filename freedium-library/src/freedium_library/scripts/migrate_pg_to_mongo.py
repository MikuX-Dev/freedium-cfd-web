"""One-shot migration: PostgreSQL `cache` table -> MongoDB `post_cache`.

Source schema:
    cache(key TEXT PRIMARY KEY, value TEXT)   -- value is raw JSON

Destination shape (handled by AsyncMongoDBCacheBackend):
    {_id, value: BinData(zstd), compression: "zstd",
     created_at, updated_at}

Usage:
    PG_DSN=postgres://user:pass@host/db \\
    MONGO_URL=mongodb://localhost:27017 \\
    python -m freedium_library.scripts.migrate_pg_to_mongo

    Optional:
        MONGO_DB         (default: freedium_cache)
        MONGO_COLLECTION (default: post_cache)
        BATCH_SIZE       (default: 1000) -- rows fetched per server-side cursor batch
        DRY_RUN=1        Read everything, write nothing.

The script is idempotent (apush upserts on _id). It is also restartable --
re-running after a crash simply re-pushes all rows.

Exit codes:
    0 - all rows migrated
    1 - configuration error (missing required env)
    2 - source DB error
    3 - destination DB error
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Iterable

from loguru import logger

import psycopg2
import psycopg2.extras

from freedium_library.utils.cache.db.mongo import AsyncMongoDBCacheBackend


PROGRESS_EVERY = 1000


def _require(env: str) -> str:
    val = os.environ.get(env)
    if not val:
        logger.error(f"missing required env var: {env}")
        sys.exit(1)
    return val


def _iter_pg_rows(dsn: str, batch_size: int) -> Iterable[tuple[str, str]]:
    """Server-side cursor yielding (key, value) pairs. Caps memory at batch_size."""
    conn = psycopg2.connect(dsn)
    try:
        # Named cursor -> server-side; avoids pulling the whole table into memory
        with conn.cursor(name="freedium_pg_to_mongo_migration") as cur:
            cur.itersize = batch_size
            cur.execute("SELECT key, value FROM cache")
            for row in cur:
                yield row[0], row[1]
    finally:
        conn.close()


async def _run() -> int:
    pg_dsn = _require("PG_DSN")
    mongo_url = _require("MONGO_URL")
    mongo_db = os.environ.get("MONGO_DB", "freedium_cache")
    mongo_collection = os.environ.get("MONGO_COLLECTION", "post_cache")
    batch_size = int(os.environ.get("BATCH_SIZE", "1000"))
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

    logger.info(
        f"migrating PG cache -> mongo {mongo_db}.{mongo_collection} "
        f"(batch={batch_size}, dry_run={dry_run})"
    )

    backend = AsyncMongoDBCacheBackend(
        connection_string=mongo_url,
        database=mongo_db,
        collection=mongo_collection,
    )
    await backend.ainit_db()

    total = 0
    started = time.monotonic()
    try:
        for key, value in _iter_pg_rows(pg_dsn, batch_size):
            if not dry_run:
                # apush handles compression + upsert
                await backend.apush(key, value)
            total += 1
            if total % PROGRESS_EVERY == 0:
                elapsed = time.monotonic() - started
                rate = total / elapsed if elapsed else 0
                logger.info(f"migrated {total} rows ({rate:.0f}/s)")
    except psycopg2.Error:
        logger.exception(f"source DB error after {total} rows")
        return 2
    except Exception:
        logger.exception(f"destination DB error after {total} rows")
        return 3
    finally:
        await backend.aclose()

    elapsed = time.monotonic() - started
    logger.info(
        f"done: {total} rows in {elapsed:.1f}s "
        f"({(total/elapsed if elapsed else 0):.0f} rows/s)"
        + (" [DRY_RUN -- nothing written]" if dry_run else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
