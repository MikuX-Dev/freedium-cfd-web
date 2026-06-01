"""Unit test for MarkdownExportService assembly (no network, fake MediumService)."""

import yaml
import pytest

from freedium_library.services.medium.markdown_export import (
    MarkdownExportService,
    _build_frontmatter,
    _build_heading,
)
from freedium_library.services.medium.renderer import PostMetadata

# 2024-03-15 and 2024-03-20 in epoch ms (UTC).
_PUBLISHED_MS = 1710460800000
_UPDATED_MS = 1710892800000


def _metadata(
    *,
    first_published_at: int | None = None,
    updated_at: int | None = None,
    is_locked: bool = False,
    title: str = "Hello World",
    subtitle: str = "A subtitle",
) -> PostMetadata:
    return PostMetadata(
        post_id="abc123",
        title=title,
        subtitle=subtitle,
        preview_image_id="",
        creator_name="Author",
        creator_id="author-id",
        creator_avatar_id=None,
        collection_name=None,
        reading_time=5,
        first_published_at=first_published_at,
        updated_at=updated_at,
        is_locked=is_locked,
        medium_url="https://medium.com/p/abc123",
        tags=["python", "testing"],
    )


class _FakeMedium:
    async def arender_with_metadata(self, url: str):
        return "body content", _metadata()


def _frontmatter_dict(md: str) -> dict:
    """Parse the leading YAML frontmatter block back into a dict."""
    assert md.startswith("---\n")
    end = md.index("\n---", 4)
    return yaml.safe_load(md[4:end])


@pytest.mark.asyncio
async def test_to_markdown_assembles_document():
    service = MarkdownExportService(_FakeMedium(), "https://freedium-mirror.cfd")  # type: ignore[arg-type]
    doc = await service.to_markdown("x")

    assert doc.content.startswith("---")
    assert "freedium_url:" in doc.content
    assert "source_url:" in doc.content
    assert "# Hello World" in doc.content
    assert "body content" in doc.content
    assert doc.filename == "hello-world.md"
    assert doc.media_type == "text/markdown; charset=utf-8"


def test_frontmatter_dates_and_free_unlocked():
    meta = _metadata(
        first_published_at=_PUBLISHED_MS,
        updated_at=_UPDATED_MS,
        is_locked=False,
    )
    fm = _build_frontmatter(meta, freedium_url="https://f", source_url="https://m")
    data = _frontmatter_dict(fm)
    assert data["published"] == "2024-03-15"
    assert data["updated"] == "2024-03-20"
    assert data["free"] is True

    heading = _build_heading(meta)
    assert "Published Mar 15, 2024" in heading
    assert "Updated Mar 20, 2024" in heading
    assert "Free: Yes" in heading


def test_frontmatter_locked_is_not_free():
    meta = _metadata(first_published_at=_PUBLISHED_MS, is_locked=True)
    fm = _build_frontmatter(meta)
    data = _frontmatter_dict(fm)
    assert data["free"] is False

    heading = _build_heading(meta)
    assert "Free: No" in heading


def test_updated_equal_to_published_is_deduped():
    meta = _metadata(
        first_published_at=_PUBLISHED_MS,
        updated_at=_PUBLISHED_MS,
        is_locked=False,
    )
    fm = _build_frontmatter(meta)
    data = _frontmatter_dict(fm)
    assert data["published"] == "2024-03-15"
    assert "updated" not in data

    heading = _build_heading(meta)
    assert "Published Mar 15, 2024" in heading
    assert "Updated" not in heading


def test_no_dates_does_not_crash():
    meta = _metadata(first_published_at=None, updated_at=None, is_locked=False)
    fm = _build_frontmatter(meta)
    data = _frontmatter_dict(fm)
    assert "published" not in data
    assert "updated" not in data
    assert data["free"] is True

    heading = _build_heading(meta)
    assert "Published" not in heading
    assert "Updated" not in heading
    assert "Free: Yes" in heading


def test_frontmatter_quotes_colons_unicode_round_trip():
    meta = _metadata(
        title='Title: with "quotes" and é unicode',
        subtitle='Sub: "tricky" — café',
    )
    fm = _build_frontmatter(meta)
    data = yaml.safe_load(fm[4 : fm.index("\n---", 4)])
    assert data["title"] == 'Title: with "quotes" and é unicode'
    assert data["subtitle"] == 'Sub: "tricky" — café'
