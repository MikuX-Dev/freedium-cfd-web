"""Tests for the shared Mongo accessor (no live Mongo needed — motor clients
construct lazily and don't connect until first use)."""
import freedium_library.utils.mongo as mongo


def test_get_collection_honors_env_and_shares_one_client(monkeypatch):
    mongo._client = None
    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGO_DB", "testdb")
    try:
        a = mongo.get_collection("foo")
        b = mongo.get_collection("bar")
        assert a.name == "foo"
        assert b.name == "bar"
        assert a.database.name == "testdb"
        # both collections are served by the same shared client instance
        assert a.database.client is b.database.client
    finally:
        mongo._client = None


def test_default_db_when_env_unset(monkeypatch):
    mongo._client = None
    monkeypatch.delenv("MONGO_DB", raising=False)
    try:
        assert mongo.get_collection("x").database.name == "freedium_cache"
    finally:
        mongo._client = None
