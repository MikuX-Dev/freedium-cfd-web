from fastapi import APIRouter
from pydantic import BaseModel, Field

from freedium_library.services.medium.gist_resolver import (
    resolve_gists_in_markdown,
)


class ResolveGistsRequest(BaseModel):
    markdown: str = Field(
        ..., description="Markdown text containing iframe gist embeds to resolve."
    )


class ResolveGistsResponse(BaseModel):
    markdown: str = Field(
        ..., description="Markdown with each gist iframe replaced by code blocks."
    )


def register_markdown_router(router: APIRouter) -> None:
    markdown_router = APIRouter(prefix="/markdown")

    async def resolve_gists(body: ResolveGistsRequest) -> ResolveGistsResponse:
        resolved = await resolve_gists_in_markdown(body.markdown)
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
