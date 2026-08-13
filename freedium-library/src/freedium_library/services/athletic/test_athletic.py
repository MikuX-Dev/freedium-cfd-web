"""URL routing + frontmatter tests for The Athletic (no network)."""
from __future__ import annotations

import pytest

from freedium_library.services.athletic.athletic import (
    AthleticService,
    _is_athletic_url,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        # The Athletic under NYT
        ("https://www.nytimes.com/athletic/7499186/2026/08/13/giants-posey/", True),
        ("https://nytimes.com/athletic/7499186/2026/08/13/giants-posey/", True),
        # collapsed scheme (proxy/SvelteKit strips a slash)
        ("https:/www.nytimes.com/athletic/7499186/2026/08/13/giants-posey/", True),
        # standalone domain
        ("https://theathletic.com/7499186/2026/08/13/giants-posey/", True),
        ("https://www.theathletic.com/7499186/", True),
        # plain NYT articles belong to NytService, not here
        ("https://www.nytimes.com/2026/06/22/us/politics/jd-vance.html", False),
        ("https://www.nytimes.com/article/some-explainer.html", False),
        ("https://cooking.nytimes.com/recipes/123-thing", False),
        # other hosts
        ("https://medium.com/@a/post-abc123", False),
        ("https://www.ft.com/content/abc", False),
        # not a URL
        ("athletic/123", False),
        ("", False),
    ],
)
def test_is_athletic_url(url: str, expected: bool) -> None:
    assert _is_athletic_url(url) is expected


def test_athletic_path_is_not_claimed_by_nyt() -> None:
    """Athletic URLs must fall through NytService so the resolver reaches
    AthleticService — the two are distinguished purely by path."""
    from freedium_library.services.nyt.nyt import _NYT_ARTICLE_RE, _normalize_url

    url = "https://www.nytimes.com/athletic/7499186/2026/08/13/giants-posey/"
    assert _NYT_ARTICLE_RE.match(_normalize_url(url)) is None


class TestFrontmatter:
    def _article(self, **over):
        base = {
            "title": "From adulation to anger",
            "excerpt": "A subtitle.",
            "permalink": "https://www.nytimes.com/athletic/1/2026/08/13/x/",
            "published_at": 1786615221000,
            "primary_tag": "MLB",
            "image_uri": "https://static01.nyt.com/athletic/uploads/a.jpg",
            "image_credit": "Getty",
            "authors": [
                {"author": {"name": "Brittany Ghiroli", "avatar_uri": "https://x/a.png"}}
            ],
        }
        base.update(over)
        return base

    def test_maps_core_fields(self):
        fm = AthleticService._frontmatter(self._article(), "https://input/")
        assert "title: From adulation to anger" in fm
        assert "name: Brittany Ghiroli" in fm
        assert "avatar: https://x/a.png" in fm
        assert "subtitle: A subtitle." in fm
        assert "publication: The Athletic" in fm
        assert "MLB" in fm
        assert "preview_image" in fm

    def test_prefers_permalink_over_input_url(self):
        fm = AthleticService._frontmatter(self._article(), "https://input/")
        assert "https://www.nytimes.com/athletic/1/2026/08/13/x/" in fm

    def test_falls_back_when_authors_missing(self):
        fm = AthleticService._frontmatter(self._article(authors=[]), "https://input/")
        assert "name: The Athletic" in fm

    def test_survives_empty_article(self):
        fm = AthleticService._frontmatter({}, "https://input/")
        assert "title: Untitled" in fm
        assert "name: The Athletic" in fm
