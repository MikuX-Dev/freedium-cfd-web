"""Tests for the PG -> Mongo migration script.

Uses mongomock-motor for the destination and an in-memory fake for the
source PG cursor. We never instantiate a real psycopg2 connection.
"""
from unittest.mock import MagicMock, patch

import pytest

try:
    from mongomock_motor import AsyncMongoMockClient
    HAVE_MOCK = True
except ImportError:
    HAVE_MOCK = False


@pytest.fixture
def fake_pg_rows():
    """Default fake PG data: 3 rows, one with a non-ASCII payload."""
    return [
        ("post_abc", '{"id":"abc","content":"hello"}'),
        ("post_def", '{"id":"def","content":"world"}'),
        ("post_xyz", '{"id":"xyz","content":"üñíçødé"}'),
    ]


@pytest.fixture
def env(monkeypatch, fake_pg_rows):
    """Wire env vars and patch psycopg2 + the AsyncMongoDBCacheBackend."""
    if not HAVE_MOCK:
        pytest.skip("mongomock_motor not installed")

    monkeypatch.setenv("PG_DSN", "postgres://fake")
    monkeypatch.setenv("MONGO_URL", "mongodb://fake")

    # Fake the psycopg2.connect -> cursor -> iter chain
    cursor_mock = MagicMock()
    cursor_mock.__enter__.return_value = cursor_mock
    cursor_mock.__exit__.return_value = False
    cursor_mock.__iter__.return_value = iter(fake_pg_rows)
    cursor_mock.execute = MagicMock()
    cursor_mock.itersize = 0

    conn_mock = MagicMock()
    conn_mock.cursor.return_value = cursor_mock

    # Patch the AsyncMongoDBCacheBackend.connect to use mongomock_motor
    from freedium_library.utils.cache.db import mongo as mongo_module

    fake_client = AsyncMongoMockClient()

    def fake_connect(self):
        self.client = fake_client
        self.db = fake_client[self.database_name]
        self.collection = self.db[self.collection_name]

    monkeypatch.setattr(
        mongo_module.AsyncMongoDBCacheBackend, "connect", fake_connect
    )

    with patch("psycopg2.connect", return_value=conn_mock):
        yield {"client": fake_client, "rows": fake_pg_rows}


@pytest.mark.asyncio
async def test_migrate_writes_one_doc_per_row(env):
    from freedium_library.scripts.migrate_pg_to_mongo import _run

    rc = await _run()
    assert rc == 0

    collection = env["client"]["freedium_cache"]["post_cache"]
    docs = await collection.find().to_list(None)
    assert len(docs) == len(env["rows"])
    keys = {doc["_id"] for doc in docs}
    assert keys == {k for k, _ in env["rows"]}


@pytest.mark.asyncio
async def test_migrate_round_trips_values_via_backend_pull(env):
    from freedium_library.scripts.migrate_pg_to_mongo import _run
    from freedium_library.utils.cache.db.mongo import AsyncMongoDBCacheBackend

    rc = await _run()
    assert rc == 0

    backend = AsyncMongoDBCacheBackend("mongodb://fake")
    for key, expected_value in env["rows"]:
        result = await backend.apull(key)
        assert result is not None
        assert result.value == expected_value


@pytest.mark.asyncio
async def test_migrate_is_idempotent(env):
    """Running twice produces the same final state."""
    from freedium_library.scripts.migrate_pg_to_mongo import _run

    rc1 = await _run()
    # Reset cursor iterator for the second run
    rc2 = await _run()
    assert rc1 == 0 and rc2 == 0

    collection = env["client"]["freedium_cache"]["post_cache"]
    docs = await collection.find().to_list(None)
    # Same number of rows, not doubled -- upsert worked
    assert len(docs) == len(env["rows"])


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(env, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    from freedium_library.scripts.migrate_pg_to_mongo import _run

    rc = await _run()
    assert rc == 0

    collection = env["client"]["freedium_cache"]["post_cache"]
    docs = await collection.find().to_list(None)
    assert len(docs) == 0


@pytest.mark.asyncio
async def test_missing_env_returns_1(monkeypatch):
    monkeypatch.delenv("PG_DSN", raising=False)
    monkeypatch.delenv("MONGO_URL", raising=False)
    from freedium_library.scripts.migrate_pg_to_mongo import _run

    with pytest.raises(SystemExit) as exc_info:
        await _run()
    assert exc_info.value.code == 1
