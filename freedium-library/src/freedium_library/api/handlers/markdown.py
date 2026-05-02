from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from freedium_library.services.medium.gist_resolver import (
    resolve_gists_in_markdown,
)


class ResolveGistsRequest(BaseModel):
    markdown: str = Field(
        ..., description="Markdown text containing iframe gist embeds to resolve."
    )
    mode: Literal["raw", "rich"] = Field(
        "raw",
        description=(
            "Resolution strategy. 'raw' (default) fetches one /raw URL per "
            "gist — bare code fence, no filename, first file only. 'rich' "
            "fetches the gist's HTML page plus each file's raw URL — "
            "preserves filename, language, and multi-file structure."
        ),
    )


class ResolveGistsResponse(BaseModel):
    markdown: str = Field(
        ..., description="Markdown with each gist iframe replaced by code blocks."
    )


def register_markdown_router(router: APIRouter) -> None:
    markdown_router = APIRouter(prefix="/markdown")

    async def resolve_gists(body: ResolveGistsRequest) -> ResolveGistsResponse:
        resolved = await resolve_gists_in_markdown(body.markdown, mode=body.mode)
        return ResolveGistsResponse(markdown=resolved)

    markdown_router.add_api_route(
        "/resolve-gists",
        endpoint=resolve_gists,
        methods=["POST"],
        summary="Inline gist iframes as code blocks",
        description=(
            "Pure transform: each `<iframe data-iframe-id=… srcdoc=…>` whose "
            "srcdoc contains a GitHub gist embed is replaced with markdown "
            "code fences for every file inside. Non-gist iframes pass through "
            "untouched. Used by the article download flow."
        ),
        tags=["markdown"],
        response_model=ResolveGistsResponse,
    )

    router.include_router(markdown_router)
