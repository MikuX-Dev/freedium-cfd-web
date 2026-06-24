"""NytService unit tests — URL validation + frontmatter assembly (no network)."""
from __future__ import annotations

import pytest

from freedium_library.services.nyt.nyt import NytService


def _svc() -> NytService:
    # Skip __init__ (no NYTClient / network needed for pure-logic tests).
    return NytService.__new__(NytService)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.nytimes.com/2026/06/22/us/politics/x.html", True),
        ("https://nytimes.com/2026/06/22/world/y.html", True),
        # proxy/SvelteKit collapse // → https:/ — must still match
        ("https:/www.nytimes.com/2026/06/22/us/politics/x.html", True),
        ("http://www.nytimes.com/2026/01/02/foo/bar.html", True),
        ("https://www.nytimes.com/interactive/2026/06/22/x.html", False),
        ("https://www.nytimes.com/live/2026/06/22/x", False),
        ("https://www.nytimes.com/section/world", False),
        ("https://medium.com/@a/post-abc123def456", False),
        # *.nytimes.com subdomains + non-date content paths
        ("https://cooking.nytimes.com/article/picnic-planning-mistakes", True),
        ("https://cooking.nytimes.com/recipes/1021234-thing", True),
        ("https://www.nytimes.com/wirecutter/reviews/best-x/", True),
        ("https://evil.com/nytimes.com/2026/06/22/x.html", False),
    ],
)
def test_is_valid(url: str, expected: bool) -> None:
    assert _svc()._is_valid(url) is expected


def test_frontmatter_maps_nyt_fields() -> None:
    raw = {
        "headline": {"__typename": "CreativeWorkHeadline", "default": "The Title", "seo": "x"},
        "summary": "A subtitle.",
        "bylines": [{"renderedRepresentation": "By Jane Doe and John Roe"}],
        "lastMajorModification": "2026-06-22T10:00:00Z",
        "firstPublishedAt": None,
        "section": {"displayName": "Politics", "name": "politics"},
    }
    fm = NytService._frontmatter(raw, "https://www.nytimes.com/2026/06/22/us/x.html")
    assert fm.startswith("---\n") and fm.rstrip().endswith("---")
    assert "title: The Title" in fm
    assert "name: Jane Doe and John Roe" in fm  # "By " stripped
    assert "subtitle: A subtitle." in fm
    assert "date: '2026-06-22T10:00:00Z'" in fm or "date: 2026-06-22" in fm
    assert "Politics" in fm
    assert "is_locked: false" in fm


def test_frontmatter_handles_missing_fields() -> None:
    fm = NytService._frontmatter({}, "https://www.nytimes.com/2026/06/22/us/x.html")
    assert "title: Untitled" in fm
    assert "The New York Times" in fm  # author fallback
