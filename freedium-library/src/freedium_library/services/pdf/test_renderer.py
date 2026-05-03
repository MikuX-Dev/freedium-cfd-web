"""Tests for render_pdf: HTML string -> PDF bytes via WeasyPrint."""
from freedium_library.services.pdf.renderer import render_pdf


def test_returns_pdf_magic_bytes():
    pdf = render_pdf("<h1>Hello</h1><p>World</p>")
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 500  # nontrivial PDFs are bigger than this


def test_handles_empty_body():
    pdf = render_pdf("<html><body></body></html>")
    assert pdf.startswith(b"%PDF-")
