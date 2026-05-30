"""render_universal: render inline when fast, hand off to the worker when slow.

These exercise the INLINE_BUDGET behavior directly on the render_universal
coroutine, mocking the service resolver (off app.state) and the TaskIQ
dispatch so no broker/network is needed.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

import freedium_library.api.handlers.render as render_mod
from freedium_library.api.handlers.render import RenderRequest, render_universal


def _http_request_with_resolver(resolver) -> Request:
    """Build a real Starlette Request whose app.state has the given resolver
    and no rendered_cache (so L2 is always a miss). render_universal is
    @beartype-typed to require a starlette Request, so a MagicMock won't do."""
    app = SimpleNamespace(
        state=SimpleNamespace(
            service_resolver=resolver,
            rendered_cache=None,
            recent_posts_service=None,
        )
    )
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/render",
        "headers": [],
        "app": app,
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_fast_inline_render_returns_markdown_no_task_id(monkeypatch):
    """A fast (L1-warm) render returns inline: markdown set, no task_id."""
    service = MagicMock()
    service.arender = AsyncMock(return_value="# Hello")
    service.arender_with_frontmatter = AsyncMock(return_value="# Hello")

    resolver = MagicMock()
    resolver.resolve = AsyncMock(return_value=("generic", service))

    # If the worker were dispatched this test would fail loudly.
    from freedium_library.tasks.cache import render_article_async
    kiq = AsyncMock(side_effect=AssertionError("must not dispatch on fast render"))
    monkeypatch.setattr(render_article_async, "kiq", kiq)

    resp = await render_universal(
        _http_request_with_resolver(resolver),
        RenderRequest(content="https://x.test/a", frontmatter=False),
    )

    assert resp.markdown == "# Hello"
    assert resp.service == "generic"
    assert resp.task_id is None
    service.arender.assert_awaited_once()


@pytest.mark.asyncio
async def test_slow_render_dispatches_to_worker(monkeypatch):
    """A render exceeding INLINE_BUDGET hands off to the TaskIQ worker and
    returns task_id + cache_status 'pending'."""
    # Make the budget tiny so the test is fast.
    monkeypatch.setattr(render_mod, "INLINE_BUDGET", 0.05)

    async def _slow(_content):
        await asyncio.sleep(5)
        return "# never"

    service = MagicMock()
    service.arender = AsyncMock(side_effect=_slow)

    resolver = MagicMock()
    resolver.resolve = AsyncMock(return_value=("generic", service))

    from freedium_library.tasks.cache import render_article_async
    kiq = AsyncMock(return_value=SimpleNamespace(task_id="task-123"))
    monkeypatch.setattr(render_article_async, "kiq", kiq)

    resp = await render_universal(
        _http_request_with_resolver(resolver),
        RenderRequest(content="https://x.test/slow", frontmatter=False),
    )

    assert resp.task_id == "task-123"
    assert resp.cache_status == "pending"
    assert resp.service == "pending"
    assert resp.markdown == ""
    kiq.assert_awaited_once()


@pytest.mark.asyncio
async def test_slow_render_broker_down_falls_back_to_full_inline(monkeypatch):
    """If the worker dispatch itself raises (broker down), serve the article
    inline without the budget rather than failing."""
    monkeypatch.setattr(render_mod, "INLINE_BUDGET", 0.05)

    calls = {"n": 0}

    async def _slow_then_ok(_content):
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(5)  # first (budgeted) call times out
            return "# never"
        return "# recovered"  # second (no-budget) call succeeds

    service = MagicMock()
    service.arender = AsyncMock(side_effect=_slow_then_ok)

    resolver = MagicMock()
    resolver.resolve = AsyncMock(return_value=("generic", service))

    from freedium_library.tasks.cache import render_article_async
    kiq = AsyncMock(side_effect=RuntimeError("broker down"))
    monkeypatch.setattr(render_article_async, "kiq", kiq)

    resp = await render_universal(
        _http_request_with_resolver(resolver),
        RenderRequest(content="https://x.test/slow", frontmatter=False),
    )

    assert resp.markdown == "# recovered"
    assert resp.service == "generic"
    assert resp.task_id is None
