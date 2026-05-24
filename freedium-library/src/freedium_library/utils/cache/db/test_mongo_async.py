"""Round-trip tests for AsyncMongoDBCacheBackend.

Uses a Mongo test double via mongomock_motor.
"""
import pytest


try:
    from mongomock_motor import AsyncMongoMockClient
    HAVE_MOCK = True
except ImportError:
    HAVE_MOCK = False


@pytest.fixture
def backend(monkeypatch):
    """Return an AsyncMongoDBCacheBackend backed by an in-memory mock."""
    if not HAVE_MOCK:
        pytest.skip("mongomock_motor not installed")

    from freedium_library.utils.cache.db.mongo import AsyncMongoDBCacheBackend

    fake_client = AsyncMongoMockClient()

    def fake_connect(self):
        self.client = fake_client
        self.db = fake_client[self.database_name]
        self.collection = self.db[self.collection_name]

    monkeypatch.setattr(AsyncMongoDBCacheBackend, "connect", fake_connect)
    return AsyncMongoDBCacheBackend("mongodb://ignored")


@pytest.mark.asyncio
async def test_push_then_pull_round_trips_string(backend):
    await backend.apush("post-123", "hello world")
    result = await backend.apull("post-123")
    assert result is not None
    assert result.key == "post-123"
    assert result.value == "hello world"


@pytest.mark.asyncio
async def test_push_dict_round_trips_as_json(backend):
    payload = {"title": "Sample", "body": "x" * 1000}
    await backend.apush("post-456", payload)
    result = await backend.apull("post-456")
    assert result is not None
    import json
    assert json.loads(result.value) == payload


@pytest.mark.asyncio
async def test_pull_missing_returns_none(backend):
    result = await backend.apull("no-such-key")
    assert result is None


@pytest.mark.asyncio
async def test_exists_reflects_push(backend):
    assert await backend.aexists("k") is False
    await backend.apush("k", "v")
    assert await backend.aexists("k") is True


@pytest.mark.asyncio
async def test_delete_removes_entry(backend):
    await backend.apush("k", "v")
    await backend.adelete("k")
    assert await backend.apull("k") is None


@pytest.mark.asyncio
async def test_stored_doc_has_zstd_marker(backend):
    """Confirm the document on disk is compressed, not raw."""
    await backend.apush("k", "x" * 5000)
    doc = await backend.collection.find_one({"_id": "k"})
    assert doc["compression"] in ("zstd", "zstd_dict_v1")
    assert isinstance(doc["value"], bytes)
    # zstd-compressed 5000 bytes of "x" should be << 5000 bytes
    assert len(doc["value"]) < 200


@pytest.mark.asyncio
async def test_compression_is_lossless(backend):
    payload = '{"complex": {"nested": ["data", 1, 2.5, true, null, "üñíçødé"]}}'
    await backend.apush("k", payload)
    result = await backend.apull("k")
    assert result.value == payload


@pytest.mark.asyncio
async def test_backward_compat_plain_zstd_documents_still_decompress(backend):
    """Documents written by the old (no-dict) backend must still pull."""
    import zstandard as zstd
    import datetime as dt

    raw = '{"hello": "world"}'
    blob = zstd.ZstdCompressor(level=19).compress(raw.encode("utf-8"))

    await backend.collection.update_one(
        {"_id": "legacy_key"},
        {
            "$set": {
                "value": blob,
                "compression": "zstd",
                "updated_at": dt.datetime.utcnow(),
            },
            "$setOnInsert": {"created_at": dt.datetime.utcnow()},
        },
        upsert=True,
    )

    result = await backend.apull("legacy_key")
    assert result is not None
    assert result.value == raw


@pytest.mark.asyncio
async def test_missing_dictionary_falls_back_to_plain_zstd(monkeypatch):
    """Simulate a deployment where dict_v1.zstd is missing — pushes should
    succeed with compression='zstd' tag instead of 'zstd_dict_v1'."""
    import freedium_library.utils.cache.db.mongo as mongo_mod

    monkeypatch.setattr(mongo_mod, "_dict", None)
    monkeypatch.setattr(mongo_mod, "_compressor_dict", None)
    monkeypatch.setattr(mongo_mod, "_decompressor_dict", None)

    blob, tag = mongo_mod._compress("hello")
    assert tag == "zstd"

    out = mongo_mod._decompress(blob, tag)
    assert out == "hello"


@pytest.mark.asyncio
async def test_unknown_compression_tag_raises(backend, monkeypatch):
    """Defensive: a document with a bogus compression tag must raise,
    not silently return garbage."""
    import datetime as dt

    await backend.collection.update_one(
        {"_id": "bad"},
        {
            "$set": {
                "value": b"xx",
                "compression": "snappy_v9000",
                "updated_at": dt.datetime.utcnow(),
            },
            "$setOnInsert": {"created_at": dt.datetime.utcnow()},
        },
        upsert=True,
    )

    with pytest.raises(ValueError, match="unknown compression tag"):
        await backend.apull("bad")
