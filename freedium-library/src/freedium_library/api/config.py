# freedium-library/src/freedium_library/api/config.py
from typing import Optional

from pydantic import Field

from freedium_library.utils.meta.pydantic import BaseConfig, BaseSettingsConfigDict


class ServerConfig(BaseConfig):
    model_config = BaseSettingsConfigDict(env_prefix="SERVER_")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=7080)
    reload: bool = Field(default=False)
    workers: Optional[int] = Field(default=None)


class APIConfig(BaseConfig):
    model_config = BaseSettingsConfigDict(env_prefix="API_")

    DISABLED_DOCS: bool = Field(default=False)
    PREFIX_PATH: str = Field(default="/api")
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=7080)
    MAX_WORKERS: int = Field(default=10)
    PDF_INTERNAL_SECRET: str = Field(
        default="dev-pdf-secret-change-in-prod",
        description="Shared secret required on POST /internal/pdf via X-Internal-Secret header.",
    )


class CacheConfig(BaseConfig):
    """Mongo-backed post-cache settings.

    The cache sits in front of Medium's GraphQL endpoint: on hit, we skip
    the upstream call entirely. CACHE_ENABLED=false disables the path so
    dev/CI environments without a Mongo instance can run cleanly.
    """

    model_config = BaseSettingsConfigDict(env_prefix="")

    CACHE_ENABLED: bool = Field(default=True)
    MONGO_URL: str = Field(default="mongodb://localhost:27017")
    MONGO_DB: str = Field(default="freedium_cache")
    MONGO_COLLECTION: str = Field(default="post_cache")
