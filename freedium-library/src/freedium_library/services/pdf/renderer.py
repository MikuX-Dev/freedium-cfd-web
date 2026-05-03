"""WeasyPrint wrapper. Pure: HTML in, PDF bytes out, no I/O."""

from __future__ import annotations

from weasyprint import HTML


def render_pdf(html_str: str) -> bytes:
    """Render a self-contained HTML string to PDF bytes.

    `base_url` is intentionally not set: callers must inline assets first
    via image_inliner.inline_images so WeasyPrint does no network I/O at
    render time. Any remaining remote URL would block the request.
    """
    return HTML(string=html_str).write_pdf()
