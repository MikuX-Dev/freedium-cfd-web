"""Tests for gist iframe parsing.

Covers the parsing layer only (no network): locating <iframe> elements in a
markdown/HTML mix, pulling the gist ref out of their srcdoc, and splicing
replacements without disturbing the surrounding markdown.
"""
from __future__ import annotations

import pytest

from freedium_library.services.medium.gist_resolver import (
    GistFile,
    GistRef,
    _extract_gist_ref,
    _find_iframes,
    _render_files,
)

GIST_SRCDOC = (
    '&lt;script src=&quot;https://gist.github.com/octocat/a1b2c3d4e5f6.js&quot;&gt;'
    "&lt;/script&gt;"
)


def _iframe(attrs: str) -> str:
    return f"<iframe {attrs}></iframe>"


class TestFindIframes:
    def test_finds_standard_iframe(self):
        md = _iframe(f'data-iframe-id="x" srcdoc="{GIST_SRCDOC}"')
        spans = _find_iframes(md)
        assert len(spans) == 1
        assert md[spans[0].start : spans[0].end] == md

    def test_attribute_order_does_not_matter(self):
        """The old regex required data-iframe-id *before* srcdoc and silently
        matched nothing otherwise."""
        md = _iframe(f'srcdoc="{GIST_SRCDOC}" data-iframe-id="x"')
        spans = _find_iframes(md)
        assert len(spans) == 1
        assert _extract_gist_ref(spans[0].srcdoc) == GistRef("octocat", "a1b2c3d4e5f6")

    def test_single_quoted_attributes(self):
        md = f"<iframe data-iframe-id='x' srcdoc='{GIST_SRCDOC}'></iframe>"
        spans = _find_iframes(md)
        assert len(spans) == 1
        assert _extract_gist_ref(spans[0].srcdoc) is not None

    def test_iframe_without_srcdoc(self):
        spans = _find_iframes('<iframe src="https://example.com"></iframe>')
        assert len(spans) == 1
        assert spans[0].srcdoc is None

    def test_no_iframes(self):
        assert _find_iframes("# Heading\n\nJust prose, no embeds.") == []

    def test_multiple_iframes_have_distinct_spans(self):
        md = f"a {_iframe(f'srcdoc=\"{GIST_SRCDOC}\"')} b {_iframe('src=\"x\"')} c"
        spans = _find_iframes(md)
        assert len(spans) == 2
        assert spans[0].end <= spans[1].start
        assert md[spans[0].start : spans[0].end].startswith("<iframe")
        assert md[spans[1].start : spans[1].end].endswith("</iframe>")

    def test_malformed_markup_does_not_raise(self):
        # A broken embed must never fail the whole export.
        assert isinstance(_find_iframes("<iframe srcdoc="), list)

    def test_spans_are_exact(self):
        prefix = "# Title\n\nSome *markdown* with `code` & an ampersand.\n\n"
        suffix = "\n\nTrailing prose > with angle brackets.\n"
        iframe = _iframe(f'srcdoc="{GIST_SRCDOC}"')
        md = prefix + iframe + suffix
        (span,) = _find_iframes(md)
        assert md[span.start : span.end] == iframe
        # Everything outside the span is untouched — this is what lets the
        # caller splice by offset instead of re-serialising the document.
        assert md[: span.start] == prefix
        assert md[span.end :] == suffix


class TestExtractGistRef:
    def test_extracts_user_and_id(self):
        assert _extract_gist_ref(
            '<script src="https://gist.github.com/octocat/a1b2c3d4e5f6.js"></script>'
        ) == GistRef("octocat", "a1b2c3d4e5f6")

    def test_ignores_non_gist_scripts(self):
        assert (
            _extract_gist_ref('<script src="https://example.com/analytics.js"></script>')
            is None
        )

    def test_ignores_lookalike_host(self):
        assert (
            _extract_gist_ref(
                '<script src="https://gist.github.com.evil.tld/u/abc123.js"></script>'
            )
            is None
        )

    def test_finds_gist_among_several_scripts(self):
        srcdoc = (
            '<script src="https://example.com/a.js"></script>'
            '<script src="https://gist.github.com/octocat/a1b2c3d4e5f6.js"></script>'
        )
        assert _extract_gist_ref(srcdoc) == GistRef("octocat", "a1b2c3d4e5f6")

    def test_empty_srcdoc(self):
        assert _extract_gist_ref("") is None


class TestRenderFiles:
    def test_named_file_gets_header_and_language(self):
        out = _render_files([GistFile(code="print(1)", filename="a.py", lang="python")])
        assert "**a.py**" in out
        assert "```python" in out
        assert "print(1)" in out

    def test_unnamed_file_gets_bare_fence(self):
        out = _render_files([GistFile(code="print(1)")])
        assert "**" not in out
        assert out.startswith("```")

    def test_multiple_files_are_separated(self):
        out = _render_files(
            [GistFile(code="a", filename="a.py"), GistFile(code="b", filename="b.py")]
        )
        assert "**a.py**" in out and "**b.py**" in out


@pytest.mark.asyncio
async def test_markdown_without_gists_is_returned_unchanged():
    from freedium_library.services.medium.gist_resolver import resolve_gists_in_markdown

    md = "# Title\n\nProse with an <iframe src=\"https://example.com\"></iframe> embed.\n"
    assert await resolve_gists_in_markdown(md) == md
