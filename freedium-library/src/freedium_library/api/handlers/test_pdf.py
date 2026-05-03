"""Integration tests for POST /internal/pdf."""
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from freedium_library.api.handlers.pdf import register_pdf_router


def _make_app(secret: str = "test-secret") -> TestClient:
    """Build a minimal FastAPI app with just the PDF router mounted."""
    app = FastAPI()
    router = APIRouter()
    register_pdf_router(router, secret=secret)
    app.include_router(router)
    return TestClient(app)


def test_rejects_missing_secret():
    client = _make_app()
    res = client.post("/internal/pdf", json={"html": "<p>x</p>", "filename": "x.pdf"})
    assert res.status_code in (401, 403, 422)  # 422 if header is required field


def test_rejects_wrong_secret():
    client = _make_app(secret="real-secret")
    res = client.post(
        "/internal/pdf",
        json={"html": "<p>x</p>", "filename": "x.pdf"},
        headers={"X-Internal-Secret": "WRONG"},
    )
    assert res.status_code == 403


def test_accepts_correct_secret_returns_pdf():
    client = _make_app(secret="real-secret")
    res = client.post(
        "/internal/pdf",
        json={"html": "<h1>Hello</h1>", "filename": "hello.pdf"},
        headers={"X-Internal-Secret": "real-secret"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert 'filename="hello.pdf"' in res.headers["content-disposition"]
    assert res.content.startswith(b"%PDF-")


def test_inlines_images_before_render(httpx_mock):
    """Smoke-test that the endpoint hands HTML through inline_images.

    We assert no exception and a valid PDF; deeper image-inlining behavior
    is covered in test_image_inliner.py.
    """
    httpx_mock.add_response(
        url="https://cdn.example.com/a.png",
        content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
        headers={"content-type": "image/png"},
    )
    client = _make_app(secret="s")
    res = client.post(
        "/internal/pdf",
        json={
            "html": '<img src="https://cdn.example.com/a.png">',
            "filename": "img.pdf",
        },
        headers={"X-Internal-Secret": "s"},
    )
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")
