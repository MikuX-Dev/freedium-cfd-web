import datetime as _dt
from typing import Union

import pymongo
import zstandard as zstd
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient

from freedium_library.utils.json import json

from ..models import CacheResponse
from .base import AbstractCacheBackend


# Cache is write-once / read-many. Level 19 costs ~3-10x more CPU at write
# time (one-shot per cache miss) but adds ~25-40% to the compression ratio
# vs. level 3. Decompression speed is level-independent.
import importlib.resources as _resources


_ZSTD_LEVEL = 19
_DICT_FILENAME = "dict_v1.zstd"
_DICT_COMPRESSION_TAG = "zstd_dict_v1"
_PLAIN_COMPRESSION_TAG = "zstd"


def _load_dict() -> "zstd.ZstdCompressionDict | None":
    """Load the bundled dictionary if it exists and is non-empty.

    Returns None on missing/empty/corrupt dict; callers fall back to
    plain (no-dict) zstd compression.
    """
    try:
        pkg_root = _resources.files("freedium_library.utils.cache.db")
        path = pkg_root / _DICT_FILENAME
        with path.open("rb") as fh:
            blob = fh.read()
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        return None
    if not blob:
        return None
    try:
        return zstd.ZstdCompressionDict(blob)
    except zstd.ZstdError:
        return None


_dict = _load_dict()

if _dict is not None:
    _compressor_dict = zstd.ZstdCompressor(level=_ZSTD_LEVEL, dict_data=_dict)
    _decompressor_dict = zstd.ZstdDecompressor(dict_data=_dict)
else:
    _compressor_dict = None
    _decompressor_dict = None

_compressor_plain = zstd.ZstdCompressor(level=_ZSTD_LEVEL)
_decompressor_plain = zstd.ZstdDecompressor()


def _compress(value_str: str) -> tuple[bytes, str]:
    """Compress value_str. Returns (blob, compression_tag).

    Uses the trained dictionary when available; falls back to plain zstd
    when the dictionary file is missing or unreadable.
    """
    raw = value_str.encode("utf-8")
    if _compressor_dict is not None:
        return _compressor_dict.compress(raw), _DICT_COMPRESSION_TAG
    return _compressor_plain.compress(raw), _PLAIN_COMPRESSION_TAG


def _decompress(blob: bytes, compression_tag: str) -> str:
    """Decompress blob according to the on-document compression tag.

    Supports both 'zstd_dict_v1' (uses bundled dict) and 'zstd' (plain).
    """
    if compression_tag == _DICT_COMPRESSION_TAG:
        if _decompressor_dict is None:
            raise RuntimeError(
                f"Document tagged {_DICT_COMPRESSION_TAG} but no "
                f"dictionary available — was dict_v1.zstd shipped?"
            )
        return _decompressor_dict.decompress(blob).decode("utf-8")
    if compression_tag == _PLAIN_COMPRESSION_TAG:
        return _decompressor_plain.decompress(blob).decode("utf-8")
    raise ValueError(f"unknown compression tag: {compression_tag!r}")


class MongoDBCacheBackend(AbstractCacheBackend):
    def __init__(
        self,
        connection_string: str,
        database: str = "freedium_cache",
        collection: str = "cache",
    ):
        self.connection_string = connection_string
        self.database_name = database
        self.collection_name = collection
        self.client = None
        self.db = None
        self.collection = None
        self.connect()

    def connect(self):
        self.client = pymongo.MongoClient(self.connection_string)
        self.db = self.client[self.database_name]
        self.collection = self.db[self.collection_name]

    def ensure_connection(self):
        if self.client is None:
            self.connect()

    def init_db(self):
        self.ensure_connection()
        self.collection.create_index("key", unique=True)

    def all(self):
        self.ensure_connection()
        return list(self.collection.find())

    def all_length(self) -> int:
        self.ensure_connection()
        return self.collection.count_documents({})

    def random(self, size: int) -> list[CacheResponse]:
        self.ensure_connection()
        pipeline = [{"$sample": {"size": size}}]
        results = self.collection.aggregate(pipeline)
        return [CacheResponse(doc["key"], doc["value"]) for doc in results]

    def pull(self, key: str) -> Union[CacheResponse, None]:
        self.ensure_connection()
        doc = self.collection.find_one({"key": key})
        if doc:
            logger.debug("Value found in DB, returning it")
            return CacheResponse(key, doc["value"])
        logger.debug(f"No value found for key: {key}")
        return None

    def push(self, key: str, value: Union[str, dict]) -> None:
        if isinstance(value, dict):
            value = json.dumps(value)
        elif not isinstance(value, str):
            raise ValueError(
                f"value argument should be a string or dict, not {type(value).__name__}"
            )

        self.ensure_connection()
        self.collection.update_one(
            {"key": key}, {"$set": {"key": key, "value": value}}, upsert=True
        )

    def delete(self, key: str) -> None:
        self.ensure_connection()
        result = self.collection.delete_one({"key": key})
        if result.deleted_count > 0:
            logger.debug(f"Deleted key: {key}")
        else:
            logger.warning(f"Attempted to delete non-existing key: {key}")

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            self.collection = None


class AsyncMongoDBCacheBackend(AbstractCacheBackend):
    """Async Mongo cache with transparent zstd compression.

    Documents:
        {
            "_id": <post_id>,
            "value": BinData(zstd-compressed JSON),
            "compression": "zstd",
            "created_at": ISODate,
            "updated_at": ISODate,
        }
    """

    def __init__(
        self,
        connection_string: str,
        database: str = "freedium_cache",
        collection: str = "post_cache",
    ):
        self.connection_string = connection_string
        self.database_name = database
        self.collection_name = collection
        self.client: AsyncIOMotorClient | None = None
        self.db = None
        self.collection = None
        self.connect()

    def connect(self) -> None:
        self.client = AsyncIOMotorClient(self.connection_string)
        self.db = self.client[self.database_name]
        self.collection = self.db[self.collection_name]

    def ensure_connection(self) -> None:
        if self.client is None:
            self.connect()

    async def aensure_connection(self) -> None:
        if self.client is None:
            self.connect()

    def init_db(self) -> None:
        """Idempotent; _id is implicitly indexed. No-op kept for symmetry."""
        self.ensure_connection()

    async def ainit_db(self) -> None:
        """Idempotent; _id is implicitly indexed. No-op kept for symmetry."""
        await self.aensure_connection()

    def all(self):
        raise NotImplementedError("Use aall() on AsyncMongoDBCacheBackend")

    async def aall(self):
        await self.aensure_connection()
        return await self.collection.find().to_list(None)

    def all_length(self) -> int:
        raise NotImplementedError("Use aall_length() on AsyncMongoDBCacheBackend")

    async def aall_length(self) -> int:
        await self.aensure_connection()
        return await self.collection.count_documents({})

    def random(self, size: int) -> list[CacheResponse]:
        raise NotImplementedError("Use arandom() on AsyncMongoDBCacheBackend")

    async def arandom(self, size: int) -> list[CacheResponse]:
        await self.aensure_connection()
        pipeline = [{"$sample": {"size": size}}]
        results = await self.collection.aggregate(pipeline).to_list(None)
        out = []
        for doc in results:
            compression = doc.get("compression", _PLAIN_COMPRESSION_TAG)
            out.append(CacheResponse(doc["_id"], _decompress(doc["value"], compression)))
        return out

    def pull(self, key: str) -> Union[CacheResponse, None]:
        raise NotImplementedError("Use apull() on AsyncMongoDBCacheBackend")

    async def apull(self, key: str) -> Union[CacheResponse, None]:
        await self.aensure_connection()
        doc = await self.collection.find_one({"_id": key})
        if doc is None:
            logger.debug(f"No value found for key: {key}")
            return None
        logger.debug("Value found in DB, returning it")
        compression = doc.get("compression", _PLAIN_COMPRESSION_TAG)
        return CacheResponse(key, _decompress(doc["value"], compression))

    def push(self, key: str, value: Union[str, dict]) -> None:
        raise NotImplementedError("Use apush() on AsyncMongoDBCacheBackend")

    async def apush(self, key: str, value: Union[str, dict]) -> None:
        if isinstance(value, dict):
            value_str = json.dumps(value)
        elif isinstance(value, str):
            value_str = value
        else:
            raise ValueError(
                f"value argument should be a string or dict, not {type(value).__name__}"
            )

        await self.aensure_connection()
        blob, compression_tag = _compress(value_str)
        now = _dt.datetime.utcnow()
        await self.collection.update_one(
            {"_id": key},
            {
                "$set": {
                    "value": blob,
                    "compression": compression_tag,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def aexists(self, key: str) -> bool:
        await self.aensure_connection()
        return await self.collection.count_documents({"_id": key}, limit=1) > 0

    def delete(self, key: str) -> None:
        raise NotImplementedError("Use adelete() on AsyncMongoDBCacheBackend")

    async def adelete(self, key: str) -> None:
        await self.aensure_connection()
        result = await self.collection.delete_one({"_id": key})
        if result.deleted_count > 0:
            logger.debug(f"Deleted key: {key}")
        else:
            logger.warning(f"Attempted to delete non-existing key: {key}")

    def close(self) -> None:
        raise NotImplementedError("Use aclose() on AsyncMongoDBCacheBackend")

    async def aclose(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            self.collection = None
