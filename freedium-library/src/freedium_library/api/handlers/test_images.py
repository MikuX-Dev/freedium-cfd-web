"""Tests for the public image-proxy endpoint GET /img/{width}/{image_id}."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import freedium_library.api.handlers.images as images
from freedium_library.api.app import create_application


def _client() -> TestClient:
    return TestClient(create_application())


class _FakeBackend:
    """Records aput calls; aget behaviour is configurable."""

    def __init__(self, get_result=None):
        self._get_result = get_result
        self.put_calls: list[tuple[str, bytes, str]] = []

    async def aget(self, key: str):
        return self._get_result

    async def aput(self, key: str, data: bytes, content_type: str) -> None:
        self.put_calls.append((key, data, content_type))


class _FakeStream:
    """Stand-in for the object returned by httpx.AsyncClient.stream(...)."""

    def __init__(self, status_code: int, content: bytes, content_type: str):
        self.status_code = status_code
        self._content = content
        self.headers = {"content-type": content_type, "content-length": str(len(content))}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_bytes(self):
        yield self._content


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient whose .stream() yields a canned body."""

    response: _FakeStream | None = None
    requested_urls: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method: str, url: str):
        _FakeAsyncClient.requested_urls.append(url)
        assert _FakeAsyncClient.response is not None
        return _FakeAsyncClient.response


def test_unsupported_width_returns_400():
    res = _client().get("/img/123/0xabc")
    assert res.status_code == 400


def test_invalid_image_id_returns_400():
    # '!' is not in the allowed character class → regex rejects → 400.
    res = _client().get("/img/700/bad!id")
    assert res.status_code == 400


def test_cache_hit_returns_bytes_without_fetching(monkeypatch):
    backend = _FakeBackend(get_result=(b"\x89PNG\r\n", "image/png"))
    monkeypatch.setattr(images, "_get_backend", lambda: backend)

    # Make any accidental httpx call explode so a hit never fetches.
    def _boom(*a, **k):
        raise AssertionError("httpx.AsyncClient must not be used on a cache hit")

    monkeypatch.setattr(images.httpx, "AsyncClient", _boom)

    res = _client().get("/img/700/0*abc")
    assert res.status_code == 200
    assert res.content == b"\x89PNG\r\n"
    assert res.headers["content-type"] == "image/png"
    assert res.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_cache_miss_fetches_stores_and_returns(monkeypatch):
    backend = _FakeBackend(get_result=None)
    monkeypatch.setattr(images, "_get_backend", lambda: backend)

    _FakeAsyncClient.response = _FakeStream(200, b"JPEGDATA", "image/jpeg")
    _FakeAsyncClient.requested_urls = []
    monkeypatch.setattr(images.httpx, "AsyncClient", _FakeAsyncClient)

    res = _client().get("/img/700/0*abc")
    assert res.status_code == 200
    assert res.content == b"JPEGDATA"
    assert res.headers["content-type"] == "image/jpeg"
    assert res.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert res.headers["x-content-type-options"] == "nosniff"

    # Fetched from the hardcoded Medium upstream.
    assert _FakeAsyncClient.requested_urls == [
        "https://miro.medium.com/v2/resize:fit:700/0*abc"
    ]
    # Stored under "{width}:{image_id}" with the upstream content-type.
    assert backend.put_calls == [("700:0*abc", b"JPEGDATA", "image/jpeg")]


def test_svg_content_type_is_rejected(monkeypatch):
    """An image/svg+xml upstream must NOT be served (stored-XSS guard)."""
    backend = _FakeBackend(get_result=None)
    monkeypatch.setattr(images, "_get_backend", lambda: backend)

    _FakeAsyncClient.response = _FakeStream(200, b"<svg onload=alert(1)>", "image/svg+xml")
    _FakeAsyncClient.requested_urls = []
    monkeypatch.setattr(images.httpx, "AsyncClient", _FakeAsyncClient)

    res = _client().get("/img/700/0*abc")
    assert res.status_code == 502
    assert backend.put_calls == []  # never cached
