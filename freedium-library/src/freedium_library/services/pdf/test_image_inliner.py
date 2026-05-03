"""Tests for inline_images: walk HTML, replace remote img src/srcset with data: URIs."""
import base64

import pytest

from freedium_library.services.pdf.image_inliner import inline_images


@pytest.mark.asyncio
async def test_inlines_simple_img(httpx_mock):
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16  # short fake PNG
    httpx_mock.add_response(
        url="https://cdn.example.com/a.png",
        content=png_bytes,
        headers={"content-type": "image/png"},
    )

    html_in = '<p>x</p><img src="https://cdn.example.com/a.png" alt="a">'
    out = await inline_images(html_in)

    expected_b64 = base64.b64encode(png_bytes).decode("ascii")
    assert f"data:image/png;base64,{expected_b64}" in out
    assert "https://cdn.example.com/a.png" not in out
