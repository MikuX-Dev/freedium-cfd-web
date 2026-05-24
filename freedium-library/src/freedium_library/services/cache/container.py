"""Dependency-injector container for the post cache backend.

Kept in its own container (rather than folded into MediumContainer) so
future services can consume the same Mongo singleton without reaching
through MediumContainer's surface.
"""
from dependency_injector import containers, providers

from freedium_library.api.config import CacheConfig
from freedium_library.utils.cache.db.mongo import AsyncMongoDBCacheBackend


class CacheContainer(containers.DeclarativeContainer):
    config = providers.Singleton(CacheConfig)

    backend = providers.Singleton(
        AsyncMongoDBCacheBackend,
        connection_string=providers.Callable(lambda c: c.MONGO_URL, config),
        database=providers.Callable(lambda c: c.MONGO_DB, config),
        collection=providers.Callable(lambda c: c.MONGO_COLLECTION, config),
    )
