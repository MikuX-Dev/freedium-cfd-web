"""Resolve embedded gist iframes into markdown code blocks.

Used at download time so the saved .md file contains the actual code
instead of a slab of HTML the user can't read on its own.

The iframes the renderer embeds carry only a `<script src="…/USER/ID.js">`
tag in their srcdoc — GitHub injects the rendered code at runtime, so
nothing useful is parseable in the static HTML. To resolve, we extract
USER+ID from the script src and fetch the canonical raw text directly:

    https://gist.githubusercontent.com/USER/ID/raw

That endpoint returns the first file's content with original whitespace
preserved, no API rate limit, no auth. It does NOT carry the filename or
language label, so the rendered code block is unlabelled and the iframe
is replaced wholesale (multi-file gists collapse to their first file).
"""

from __future__ import annotations

import asyncio
import html
import re
import time
from dataclasses import dataclass
from typing import Final

import httpx
from beartype import beartype
from loguru import logger

# <iframe ... data-iframe-id="..." ... srcdoc="..." ... ></iframe>
_IFRAME_RE: Final[re.Pattern[str]] = re.compile(
    r'<iframe\b[^>]*?data-iframe-id="([^"]+)"[^>]*?srcdoc="(.*?)"[^>]*?></iframe>',
    re.DOTALL,
)

# Inside an unescaped srcdoc: <script src="https://gist.github.com/USER/HEX.js">
_GIST_SCRIPT_RE: Final[re.Pattern[str]] = re.compile(
    r'<script[^>]*\bsrc="https://gist\.github\.com/([^/"]+)/([a-fA-F0-9]+)\.js"',
)

_RAW_BASE: Final[str] = "https://gist.githubusercontent.com"
_GIST_CACHE_TTL_SECONDS: Final[float] = 600.0
_GIST_REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0


@dataclass(slots=True, frozen=True)
class GistRef:
    user: str
    gist_id: str


_cache: dict[GistRef, tuple[float, str | None]] = {}
_cache_lock = asyncio.Lock()
_inflight: dict[GistRef, asyncio.Task[str | None]] = {}


@beartype
async def _fetch_raw(ref: GistRef, client: httpx.AsyncClient) -> str | None:
    """Fetch raw gist content. Returns None on any failure so the caller
    can leave the original iframe intact."""
    url = f"{_RAW_BASE}/{ref.user}/{ref.gist_id}/raw"
    try:
        resp = await client.get(url, timeout=_GIST_REQUEST_TIMEOUT_SECONDS)
    except httpx.RequestError as exc:
        logger.warning(
            f"Gist raw fetch error for {ref.user}/{ref.gist_id}: {exc}"
        )
        return None
    if resp.status_code != 200:
        logger.warning(
            f"Gist raw fetch failed: HTTP {resp.status_code} for "
            f"{ref.user}/{ref.gist_id}"
        )
        return None
    return resp.text or None


@beartype
async def _get_raw_cached(
    ref: GistRef, client: httpx.AsyncClient
) -> str | None:
    now = time.monotonic()
    async with _cache_lock:
        cached = _cache.get(ref)
        if cached and now - cached[0] < _GIST_CACHE_TTL_SECONDS:
            return cached[1]
        task = _inflight.get(ref)
        is_originator = task is None
        if is_originator:
            task = asyncio.create_task(_fetch_raw(ref, client))
            _inflight[ref] = task
    assert task is not None
    code = await task
    if is_originator:
        async with _cache_lock:
            _inflight.pop(ref, None)
            _cache[ref] = (time.monotonic(), code)
    return code


@beartype
def _extract_gist_ref(srcdoc_unescaped: str) -> GistRef | None:
    m = _GIST_SCRIPT_RE.search(srcdoc_unescaped)
    if not m:
        return None
    return GistRef(user=m.group(1), gist_id=m.group(2))


@beartype
def _render_block(code: str) -> str:
    return f"```\n{code.rstrip()}\n```"


@beartype
async def resolve_gists_in_markdown(markdown: str) -> str:
    """Replace each `<iframe data-iframe-id="…" srcdoc="…">` whose srcdoc
    embeds a GitHub gist with a markdown code fence containing the gist's
    raw text. Iframes that aren't gists, or whose fetch fails, pass
    through untouched.
    """
    refs: list[GistRef] = []
    seen: set[GistRef] = set()
    for m in _IFRAME_RE.finditer(markdown):
        srcdoc = html.unescape(m.group(2))
        ref = _extract_gist_ref(srcdoc)
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)

    if not refs:
        return markdown

    async with httpx.AsyncClient(
        headers={"User-Agent": "freedium/1.0"},
        follow_redirects=True,
    ) as client:
        results = await asyncio.gather(
            *[_get_raw_cached(ref, client) for ref in refs]
        )
    code_by_ref: dict[GistRef, str | None] = dict(zip(refs, results))

    def replace(match: re.Match[str]) -> str:
        srcdoc = html.unescape(match.group(2))
        ref = _extract_gist_ref(srcdoc)
        if not ref:
            return match.group(0)
        code = code_by_ref.get(ref)
        if not code:
            return match.group(0)
        return _render_block(code)

    return _IFRAME_RE.sub(replace, markdown)
