"""POST /internal/pdf - HTML body in, PDF bytes out. Internal-only.

Note: WeasyPrint accumulates state in process-level font/glyph caches.
Long-running deployments should recycle workers periodically (e.g.,
uvicorn --limit-max-requests).
"""

from __future__ import annotations

from beartype import beartype
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from loguru import logger
from pydantic import BaseModel, Field

from freedium_library.api.error_log import log_errored_link
from freedium_library.api.metrics import PDF_RENDER, track_render
from freedium_library.services.pdf.image_inliner import inline_images
from freedium_library.services.pdf.renderer import render_pdf


class PdfRequest(BaseModel):
    """Body for POST /internal/pdf."""

    html: str = Field(..., description="Self-contained HTML document to render.")
    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r'^[^\r\n"\\/]+$',
        description="Filename for Content-Disposition (no path).",
    )
    url: str | None = Field(
        default=None,
        description=(
            "Original article URL. Used only for error logging "
            "(errored-link JSONL); not validated."
        ),
    )


def _make_secret_dep(expected_secret: str):
    """Build a FastAPI dependency that validates X-Internal-Secret."""

    def _dep(x_internal_secret: str = Header(..., alias="X-Internal-Secret")) -> None:
        if x_internal_secret != expected_secret:
            raise HTTPException(status_code=403, detail="Forbidden")

    return _dep


def register_pdf_router(router: APIRouter, secret: str) -> None:
    """Mount POST /internal/pdf under `router`. `secret` is the expected
    value of the X-Internal-Secret header - typically read from config."""
    pdf_router = APIRouter(prefix="/internal")
    require_secret = _make_secret_dep(secret)

    @beartype
    async def _generate_pdf(
        req: PdfRequest,
        _: None = Depends(require_secret),
    ) -> Response:
        url = req.url or "(unknown)"
        with track_render(PDF_RENDER) as ctx:
            try:
                inlined_html = await inline_images(req.html)
            except HTTPException:
                ctx.set_outcome("pdf_failure")
                raise
            except Exception as exc:
                ctx.set_outcome("pdf_failure")
                logger.warning(f"inline_images failed: {exc!r}")
                log_errored_link(url, "pdf_failure", None, repr(exc))
                raise HTTPException(status_code=400, detail="HTML parse failed") from exc

            try:
                pdf_bytes = render_pdf(inlined_html)
            except HTTPException:
                ctx.set_outcome("pdf_failure")
                raise
            except Exception as exc:
                ctx.set_outcome("pdf_failure")
                logger.exception("WeasyPrint render failed")
                log_errored_link(url, "pdf_failure", None, repr(exc))
                raise HTTPException(status_code=502, detail="PDF render failed") from exc

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{req.filename}"',
                },
            )

    pdf_router.add_api_route(
        "/pdf",
        endpoint=_generate_pdf,
        methods=["POST"],
        summary="Generate PDF from HTML (internal)",
        description=(
            "Internal endpoint: SvelteKit posts pre-rendered HTML; "
            "Python pre-fetches images, runs WeasyPrint, returns PDF bytes. "
            "Scope note: only <img src> URLs are inlined; remote "
            "<link rel=\"stylesheet\">, @import url(...), and other "
            "asset references will still trigger network fetches at "
            "render time, so callers should send self-contained HTML "
            "with CSS embedded in <style> tags."
        ),
        tags=["internal"],
    )

    router.include_router(pdf_router)
