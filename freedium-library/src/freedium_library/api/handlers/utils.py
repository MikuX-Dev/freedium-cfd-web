from fastapi import APIRouter, FastAPI

from .articles import register_articles_router
from .iframe import register_iframe_router
from .render import register_render_router


def register_router(app: FastAPI, router_prefix: str) -> None:
    router = APIRouter(prefix=router_prefix)
    register_render_router(router)
    register_articles_router(router)
    register_iframe_router(router)

    app.include_router(router)
