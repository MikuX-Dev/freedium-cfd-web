"""Tests for cache_status field in RenderResponse."""
import json

import pytest

from freedium_library.api.handlers.render import RenderResponse


class TestRenderResponseCacheStatus:
    """Unit tests for RenderResponse.cache_status field."""

    def test_default_cache_status_is_miss(self):
        resp = RenderResponse(markdown="# Hello", service="medium")
        assert resp.cache_status == "miss"

    def test_l2_hit_embedded_when_base64_present(self):
        md = "# Hello\n\n![img](data:image/png;base64,iVBOR...)"
        has_embedded = "data:image" in md
        status = f"l2_hit_{'embedded' if has_embedded else 'cdn'}"
        resp = RenderResponse(markdown=md, service="medium", cache_status=status)
        assert resp.cache_status == "l2_hit_embedded"

    def test_l2_hit_cdn_when_no_base64(self):
        md = "# Hello\n\n![img](https://miro.medium.com/v2/img.jpg)"
        has_embedded = "data:image" in md
        status = f"l2_hit_{'embedded' if has_embedded else 'cdn'}"
        resp = RenderResponse(markdown=md, service="medium", cache_status=status)
        assert resp.cache_status == "l2_hit_cdn"

    def test_cache_status_serialized_in_json(self):
        resp = RenderResponse(
            markdown="# Test", service="medium", cache_status="l2_hit_embedded"
        )
        data = json.loads(resp.model_dump_json())
        assert data["cache_status"] == "l2_hit_embedded"
