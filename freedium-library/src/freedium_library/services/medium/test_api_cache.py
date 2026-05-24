"""End-to-end: MediumApiService hits Mongo cache on the second call."""
from unittest.mock import AsyncMock, MagicMock

import pytest


try:
    from mongomock_motor import AsyncMongoMockClient
    HAVE_MOCK = True
except ImportError:
    HAVE_MOCK = False


@pytest.fixture
def fake_mongo(monkeypatch):
    if not HAVE_MOCK:
        pytest.skip("mongomock_motor not installed")

    from freedium_library.utils.cache.db.mongo import AsyncMongoDBCacheBackend
    fake_client = AsyncMongoMockClient()

    def fake_connect(self):
        self.client = fake_client
        self.db = fake_client[self.database_name]
        self.collection = self.db[self.collection_name]

    monkeypatch.setattr(AsyncMongoDBCacheBackend, "connect", fake_connect)
    return AsyncMongoDBCacheBackend("mongodb://fake")


def _make_service(cache):
    """Build a MediumApiService with mocked request/config + the given cache."""
    from freedium_library.services.medium.api import MediumApiService

    request = MagicMock()
    config = MagicMock()
    config.cookies = None
    return MediumApiService(request=request, config=config, cache=cache)


@pytest.mark.asyncio
async def test_cache_miss_then_hit(fake_mongo, monkeypatch):
    """First call: Medium called, value stored. Second call: Medium NOT called."""
    fake_response = {"data": {"post": {"id": "post_abc", "title": "Sample"}}}
    fetch_mock = AsyncMock(return_value=fake_response)

    service = _make_service(cache=fake_mongo)
    monkeypatch.setattr(service, "query_post_graphql", fetch_mock)

    result_1 = await service.query_post_by_id("post_abc")
    result_2 = await service.query_post_by_id("post_abc")

    assert result_1 == fake_response
    # On hit we get the cached dict back (model_validate falls back to dict
    # because the fake payload isn't a real GraphQLPost shape).
    assert result_2 == fake_response
    assert fetch_mock.await_count == 1


@pytest.mark.asyncio
async def test_cache_disabled_always_hits_medium(monkeypatch):
    """With cache=None, every call hits Medium."""
    fake_response = {"data": {"post": {"id": "post_xyz"}}}
    fetch_mock = AsyncMock(return_value=fake_response)

    service = _make_service(cache=None)
    monkeypatch.setattr(service, "query_post_graphql", fetch_mock)

    await service.query_post_by_id("post_xyz")
    await service.query_post_by_id("post_xyz")

    assert fetch_mock.await_count == 2


@pytest.mark.asyncio
async def test_cache_read_failure_falls_through(fake_mongo, monkeypatch):
    """If apull raises, we still hit Medium and return successfully."""
    monkeypatch.setattr(fake_mongo, "apull", AsyncMock(side_effect=Exception("boom")))

    fake_response = {"data": {"post": {"id": "p"}}}
    fetch_mock = AsyncMock(return_value=fake_response)

    service = _make_service(cache=fake_mongo)
    monkeypatch.setattr(service, "query_post_graphql", fetch_mock)

    result = await service.query_post_by_id("p")

    assert result == fake_response
    assert fetch_mock.await_count == 1


@pytest.mark.asyncio
async def test_cache_write_failure_does_not_break_response(fake_mongo, monkeypatch):
    """If apush raises, the response is still returned to the caller."""
    monkeypatch.setattr(fake_mongo, "apush", AsyncMock(side_effect=Exception("boom")))

    fake_response = {"data": {"post": {"id": "p"}}}
    fetch_mock = AsyncMock(return_value=fake_response)

    service = _make_service(cache=fake_mongo)
    monkeypatch.setattr(service, "query_post_graphql", fetch_mock)

    result = await service.query_post_by_id("p")

    assert result == fake_response
