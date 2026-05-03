"""End-to-end: full HTML → PDF → text-extract round trip."""
import io

import pypdf
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from freedium_library.api.handlers.pdf import register_pdf_router


def _client() -> TestClient:
    app = FastAPI()
    router = APIRouter()
    register_pdf_router(router, secret="s")
    app.include_router(router)
    return TestClient(app)


def test_pdf_contains_article_title():
    """Verify the title text in the input HTML appears in the PDF text layer."""
    html = """<!doctype html>
<html><head><style>@page{size:A4;margin:2cm}</style></head>
<body><article class="prose-print" data-title="Hello World Title">
<h1>Hello World Title</h1>
<p>Body content.</p>
</article></body></html>"""

    res = _client().post(
        "/internal/pdf",
        json={"html": html, "filename": "hello.pdf"},
        headers={"X-Internal-Secret": "s"},
    )
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")

    reader = pypdf.PdfReader(io.BytesIO(res.content))
    assert len(reader.pages) >= 1
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert "Hello World Title" in text
    assert "Body content." in text
