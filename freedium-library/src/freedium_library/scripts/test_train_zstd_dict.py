"""Smoke test for the zstd dictionary training script."""
import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from mongomock_motor import AsyncMongoMockClient
    HAVE_MOCK = True
except ImportError:
    HAVE_MOCK = False


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Wire env vars + patch the AsyncMongoDBCacheBackend so we use mongomock."""
    if not HAVE_MOCK:
        pytest.skip("mongomock_motor not installed")

    monkeypatch.setenv("MONGO_URL", "mongodb://fake")
    monkeypatch.setenv("DICT_OUT_PATH", str(tmp_path / "dict_v1.zstd"))
    monkeypatch.setenv("SAMPLE_LIMIT", "1000")

    fake_client = AsyncMongoMockClient()

    with patch(
        "freedium_library.scripts.train_zstd_dict.AsyncIOMotorClient",
        return_value=fake_client,
    ):
        yield {
            "client": fake_client,
            "dict_path": tmp_path / "dict_v1.zstd",
        }


@pytest.mark.asyncio
async def test_train_with_too_few_samples_returns_2(env, monkeypatch):
    from freedium_library.scripts.train_zstd_dict import _run

    col = env["client"]["freedium_cache"]["post_cache"]
    import zstandard as zstd
    cz = zstd.ZstdCompressor(level=19)
    for i in range(50):
        await col.insert_one(
            {
                "_id": f"k{i}",
                "value": cz.compress(f'{{"i": {i}}}'.encode("utf-8")),
                "compression": "zstd",
            }
        )

    rc = await _run()
    assert rc == 2
    assert not env["dict_path"].exists()


@pytest.mark.asyncio
async def test_train_with_enough_samples_writes_dict(env, monkeypatch):
    from freedium_library.scripts.train_zstd_dict import _run

    col = env["client"]["freedium_cache"]["post_cache"]
    import zstandard as zstd
    cz = zstd.ZstdCompressor(level=19)
    template = (
        '{"data": {"post": {"id": "%s", "title": "%s", '
        '"paragraphs": [%s], "tags": ["a", "b", "c"]}}}'
    )
    for i in range(150):
        body = ", ".join(
            f'{{"text": "paragraph {j} content"}}' for j in range(20)
        )
        doc = template % (f"id_{i}", f"Title {i}", body)
        await col.insert_one(
            {
                "_id": f"k{i}",
                "value": cz.compress(doc.encode("utf-8")),
                "compression": "zstd",
            }
        )

    rc = await _run()
    assert rc == 0
    assert env["dict_path"].exists()
    assert env["dict_path"].stat().st_size > 512


@pytest.mark.asyncio
async def test_train_skips_dict_v1_docs_for_training_input(env, monkeypatch):
    """Documents already compressed with the dictionary are skipped during
    training (self-reference avoidance)."""
    from freedium_library.scripts.train_zstd_dict import _gather_samples

    col = env["client"]["freedium_cache"]["post_cache"]
    import zstandard as zstd
    cz = zstd.ZstdCompressor(level=19)

    for i in range(50):
        await col.insert_one(
            {
                "_id": f"plain_{i}",
                "value": cz.compress(f'{{"i": {i}}}'.encode("utf-8")),
                "compression": "zstd",
            }
        )
    for i in range(50):
        await col.insert_one(
            {
                "_id": f"dict_{i}",
                "value": b"\\x00",
                "compression": "zstd_dict_v1",
            }
        )

    samples = await _gather_samples(
        env["client"], "freedium_cache", "post_cache", 1000
    )
    assert len(samples) == 50
