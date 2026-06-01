"""Unit test for MarkdownExportService assembly (no network, fake MediumService)."""

import pytest

from freedium_library.services.medium.markdown_export import MarkdownExportService
from freedium_library.services.medium.renderer import PostMetadata


def _metadata() -> PostMetadata:
    return PostMetadata(
        post_id="abc123",
        title="Hello World",
        subtitle="A subtitle",
        preview_image_id="",
        creator_name="Author",
        creator_id="author-id",
        creator_avatar_id=None,
        collection_name=None,
        reading_time=5,
        first_published_at=None,
        updated_at=None,
        is_locked=False,
        medium_url="https://medium.com/p/abc123",
        tags=["python", "testing"],
    )


class _FakeMedium:
    async def arender_with_metadata(self, url: str):
        return "body content", _metadata()


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
