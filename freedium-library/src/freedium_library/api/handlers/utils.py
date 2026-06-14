from fastapi import APIRouter, FastAPI

from freedium_library.api.config import APIConfig

from .articles import register_articles_router
from .download import register_download_router
from .memtrace import register_memtrace_router
from .pdf import register_pdf_router
from .render import register_render_router


def register_router(
    app: FastAPI,
    router_prefix: str,
    *,
    config: APIConfig | None = None,
) -> None:
    router = APIRouter(prefix=router_prefix)
    register_render_router(router)
    register_articles_router(router)
    register_download_router(router)

    # Single /internal sub-router holding pdf + memtrace. Two separate routers
    # both prefixed /internal produced overlapping _IncludedRouter entries that
    # crash prometheus_fastapi_instrumentator's route-name resolver; one shared
    # router (like the other sub-routers) avoids it.
    secret = (config or APIConfig()).PDF_INTERNAL_SECRET
    internal_router = APIRouter(prefix="/internal")
    register_pdf_router(internal_router, secret=secret)
    register_memtrace_router(internal_router, secret=secret)
    router.include_router(internal_router)

    app.include_router(router)
