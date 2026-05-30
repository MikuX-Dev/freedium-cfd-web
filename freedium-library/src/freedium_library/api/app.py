import os

from fastapi import FastAPI
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator

# ------------------------------------------------------------------
# Replace asyncio's default event loop with libuv (Linux-only).
# On async-IO-heavy workloads — WARP-proxied GraphQL fetches, Mongo
# cache reads/writes, Redis pipeline ops — uvloop typically reduces
# per-request CPU by 20-40 % vs. the pure-Python asyncio loop.
# ------------------------------------------------------------------
try:
    import uvloop
    uvloop.install()
except ImportError:
    pass  # macOS / Windows dev machine — not a problem

# Multiprocess Prometheus support: each uvicorn worker writes to a shared
# mmap'd directory. The /metrics endpoint aggregates all workers.
_MULTIPROC_DIR = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
if _MULTIPROC_DIR:
    os.makedirs(_MULTIPROC_DIR, exist_ok=True)

from freedium_library.api import metrics as _metrics  # noqa: F401  # registers Prom metrics
from freedium_library.api.container import APIContainer
from freedium_library.api.error import register_error_handler
from freedium_library.api.handlers import register_router
from freedium_library.api.lifespan import lifespan
from freedium_library.api.middlewares import register_middlewares
from freedium_library.api.settings import ApplicationSettings
from fastapi.openapi.utils import get_openapi


def custom_openapi(app: FastAPI):
    """
    Customize the OpenAPI schema to remove the HEAD method.
    """
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    for path in openapi_schema.get("paths", {}):
        if "head" in openapi_schema["paths"][path]:
            del openapi_schema["paths"][path]["head"]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


def create_application() -> FastAPI:
    api_container = APIContainer()

    settings = ApplicationSettings(container=api_container)
    config = api_container.config()

    if config.DISABLED_DOCS:
        logger.warning(f"Documentation is disabled: {config.DISABLED_DOCS}")
        settings.disable_docs()

    app = FastAPI(
        title=settings.title,
        version=settings.version,
        openapi_url=settings.openapi_url,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        lifespan=lifespan,
    )

    register_router(app, settings.prefix_path, config=config)

    @app.get("/healthz", include_in_schema=False)
    def _healthz() -> dict[str, str]:
        return {"status": "ok"}

    register_error_handler(app)
    register_middlewares(app)

    app.openapi = lambda: custom_openapi(app)

    Instrumentator(
        excluded_handlers=["/metrics", "/healthz"],
        should_group_status_codes=False,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    if _MULTIPROC_DIR:
        from prometheus_client import CollectorRegistry, generate_latest, multiprocess, CONTENT_TYPE_LATEST
        from fastapi.responses import Response as FastAPIResponse

        @app.get("/metrics", include_in_schema=False)
        def _metrics_multiproc():
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            data = generate_latest(registry)
            return FastAPIResponse(content=data, media_type=CONTENT_TYPE_LATEST)

    return app


app = create_application()
