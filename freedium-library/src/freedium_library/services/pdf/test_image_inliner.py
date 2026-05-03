"""Tests for inline_images: walk HTML, replace remote img src with data: URIs."""
import base64

import httpx
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
    assert "<p>x</p>" in out
    assert 'alt="a"' in out


@pytest.mark.asyncio
async def test_preserves_leading_text_position(httpx_mock):
    """Regression: text appearing before any tag must stay at the start."""
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    httpx_mock.add_response(
        url="https://cdn.example.com/lead.png",
        content=png_bytes,
        headers={"content-type": "image/png"},
    )
    html_in = 'Leading text before tags. <img src="https://cdn.example.com/lead.png">'
    out = await inline_images(html_in)
    assert out.startswith("Leading text before tags.")


@pytest.mark.asyncio
async def test_404_falls_back_to_placeholder(httpx_mock):
    httpx_mock.add_response(url="https://cdn.example.com/missing.png", status_code=404)
    out = await inline_images('<img src="https://cdn.example.com/missing.png">')
    assert "data:image/svg+xml;base64," in out
    assert "https://cdn.example.com/missing.png" not in out


@pytest.mark.asyncio
async def test_timeout_falls_back_to_placeholder(httpx_mock):
    httpx_mock.add_exception(httpx.ReadTimeout("slow"))
    out = await inline_images('<img src="https://cdn.example.com/slow.png">')
    assert "data:image/svg+xml;base64," in out


@pytest.mark.asyncio
async def test_oversize_falls_back_to_placeholder(httpx_mock):
    huge = b"x" * 6_000_000  # > MAX_IMAGE_BYTES
    httpx_mock.add_response(
        url="https://cdn.example.com/huge.png",
        content=huge,
        headers={"content-type": "image/png"},
    )
    out = await inline_images('<img src="https://cdn.example.com/huge.png">')
    assert "data:image/svg+xml;base64," in out
    # Confirm the huge body is NOT base64-embedded
    assert base64.b64encode(b"x" * 1000).decode("ascii") not in out


@pytest.mark.asyncio
async def test_no_images_passthrough():
    html = "<p>no images here</p>"
    out = await inline_images(html)
    assert out == html


@pytest.mark.asyncio
async def test_relative_and_data_urls_left_alone():
    html = '<img src="/local.png"><img src="data:image/png;base64,AA==">'
    # No httpx_mock setup -> any real fetch would error
    out = await inline_images(html)
    assert "/local.png" in out
    assert "data:image/png;base64,AA==" in out
