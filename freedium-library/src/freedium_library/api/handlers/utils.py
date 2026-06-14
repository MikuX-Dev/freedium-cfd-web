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
    register_pdf_router(router, secret=(config or APIConfig()).PDF_INTERNAL_SECRET)
    register_memtrace_router(router, secret=(config or APIConfig()).PDF_INTERNAL_SECRET)

    app.include_router(router)
