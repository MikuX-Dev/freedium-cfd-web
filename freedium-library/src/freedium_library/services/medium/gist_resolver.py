"""Resolve embedded gist iframes into markdown code blocks.

Used at download time so the saved .md file contains the actual code
instead of a slab of HTML the user can't read on its own.

Two resolution strategies are provided as separate services:

* `RawGistResolver` — single GET to
  `gist.githubusercontent.com/USER/ID/raw`. Fast, no parsing, but
  emits a bare ` ``` ` fence (no filename, no language) and only
  returns the first file of multi-file gists.

* `RichGistResolver` — GET the gist's HTML page to enumerate every
  file's "view raw" link (which embeds filename + commit SHA) and
  language, then GET each raw URL in parallel. More requests, but
  preserves filenames, language tags, and multi-file structure.

Both share the iframe matching and caching scaffolding via a private
`_CachedResolver` base. `resolve_gists_in_markdown(md, mode=…)` is the
entry point — `mode="raw"` (default) or `mode="rich"`.
"""

from __future__ import annotations

import asyncio
import html
import re
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, Final, Literal, Protocol, runtime_checkable

import httpx
from beartype import beartype
from bs4 import BeautifulSoup, Tag
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

ResolverMode = Literal["raw", "rich"]


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class GistRef:
    user: str
    gist_id: str


@dataclass(slots=True, frozen=True)
class GistFile:
    """A single resolved file. `filename` and `lang` may be empty when the
    resolver doesn't expose them (e.g. the raw resolver)."""

    code: str
    filename: str = ""
    lang: str = ""


@runtime_checkable
class GistResolver(Protocol):
    """Strategy interface for fetching a gist's files."""

    async def fetch(
        self, ref: GistRef, client: httpx.AsyncClient
    ) -> list[GistFile] | None: ...


# ---------------------------------------------------------------------------
# Language inference (used by RichGistResolver)
# ---------------------------------------------------------------------------


_EXT_TO_LANG: Final[dict[str, str]] = {
    "py": "python",
    "js": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "jsx": "jsx",
    "ts": "typescript",
    "tsx": "tsx",
    "rb": "ruby",
    "sh": "bash",
    "bash": "bash",
    "zsh": "bash",
    "fish": "fish",
    "md": "markdown",
    "yml": "yaml",
    "yaml": "yaml",
    "json": "json",
    "toml": "toml",
    "xml": "xml",
    "html": "html",
    "htm": "html",
    "css": "css",
    "scss": "scss",
    "sass": "sass",
    "cs": "csharp",
    "go": "go",
    "rs": "rust",
    "java": "java",
    "kt": "kotlin",
    "swift": "swift",
    "cpp": "cpp",
    "cxx": "cpp",
    "cc": "cpp",
    "c": "c",
    "h": "c",
    "hpp": "cpp",
    "php": "php",
    "sql": "sql",
}

_GH_LANG_OVERRIDES: Final[dict[str, str]] = {
    "c++": "cpp",
    "c#": "csharp",
    "f#": "fsharp",
    "objective-c": "objectivec",
    "shell": "bash",
}


@beartype
def _infer_lang(filename: str, gh_language: str | None = None) -> str:
    if gh_language:
        key = gh_language.strip().lower()
        if key in _GH_LANG_OVERRIDES:
            return _GH_LANG_OVERRIDES[key]
        if key and key.replace("-", "").replace("+", "").isalnum():
            return key
    lower = filename.lower()
    if lower == "dockerfile":
        return "dockerfile"
    if lower == "makefile":
        return "makefile"
    ext = lower.rsplit(".", 1)[-1] if "." in lower else ""
    return _EXT_TO_LANG.get(ext, "")


# ---------------------------------------------------------------------------
# Rendering + iframe parsing helpers
# ---------------------------------------------------------------------------


@beartype
def _extract_gist_ref(srcdoc_unescaped: str) -> GistRef | None:
    m = _GIST_SCRIPT_RE.search(srcdoc_unescaped)
    if not m:
        return None
    return GistRef(user=m.group(1), gist_id=m.group(2))


@beartype
def _render_files(files: list[GistFile]) -> str:
    """Format files as markdown. Files with a filename get a bold header
    above a labelled code fence; files without (raw resolver) get a bare
    fence."""
    parts: list[str] = []
    for f in files:
        if f.filename:
            parts.append(f"**{f.filename}**\n\n```{f.lang}\n{f.code}\n```")
        else:
            parts.append(f"```{f.lang}\n{f.code}\n```")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Cache scaffolding shared by both resolver implementations
# ---------------------------------------------------------------------------


_DEFAULT_TTL_SECONDS: Final[float] = 600.0
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 10.0


@dataclass(slots=True)
class _CachedResolver:
    """Per-instance TTL cache + inflight dedup. Subclasses implement
    `_do_fetch` and call `_get_cached` from their public `fetch`."""

    ttl_seconds: float = _DEFAULT_TTL_SECONDS
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    _cache: dict[GistRef, tuple[float, list[GistFile] | None]] = field(
        default_factory=dict, init=False, repr=False
    )
    _inflight: dict[GistRef, asyncio.Task[list[GistFile] | None]] = field(
        default_factory=dict, init=False, repr=False
    )
    _lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False
    )

    async def _get_cached(
        self,
        ref: GistRef,
        fetcher: Callable[
            [], Coroutine[Any, Any, list[GistFile] | None]
        ],
    ) -> list[GistFile] | None:
        now = time.monotonic()
        async with self._lock:
            cached = self._cache.get(ref)
            if cached and now - cached[0] < self.ttl_seconds:
                return cached[1]
            task = self._inflight.get(ref)
            is_originator = task is None
            if is_originator:
                task = asyncio.create_task(fetcher())
                self._inflight[ref] = task
        assert task is not None
        files = await task
        if is_originator:
            async with self._lock:
                self._inflight.pop(ref, None)
                self._cache[ref] = (time.monotonic(), files)
        return files


# ---------------------------------------------------------------------------
# Strategy: raw — single GET, no metadata
# ---------------------------------------------------------------------------


_RAW_BASE: Final[str] = "https://gist.githubusercontent.com"


class RawGistResolver(_CachedResolver):
    """Fetch only `gist.githubusercontent.com/USER/ID/raw` — one request
    per gist, plain text/plain response, no parsing.

    Costs: no filename label, no language tag, multi-file gists collapse
    to their first file. Simplest path; fastest for single-file gists.
    """

    async def fetch(
        self, ref: GistRef, client: httpx.AsyncClient
    ) -> list[GistFile] | None:
        return await self._get_cached(ref, lambda: self._fetch(ref, client))

    async def _fetch(
        self, ref: GistRef, client: httpx.AsyncClient
    ) -> list[GistFile] | None:
        url = f"{_RAW_BASE}/{ref.user}/{ref.gist_id}/raw"
        try:
            resp = await client.get(url, timeout=self.timeout_seconds)
        except httpx.RequestError as exc:
            logger.warning(
                f"Raw gist fetch error for {ref.user}/{ref.gist_id}: {exc}"
            )
            return None
        if resp.status_code != 200:
            logger.warning(
                f"Raw gist fetch failed: HTTP {resp.status_code} for "
                f"{ref.user}/{ref.gist_id}"
            )
            return None
        text = resp.text
        if not text:
            return None
        return [GistFile(code=text)]


# ---------------------------------------------------------------------------
# Strategy: rich — HTML page + per-file raw URLs
# ---------------------------------------------------------------------------


_GIST_BASE: Final[str] = "https://gist.github.com"


@beartype
def _extract_lang_from_block(file_block: Tag) -> str:
    """GitHub stamps the language onto each .blob-wrapper as `type-<lang>`."""
    for el in file_block.select("[class*='type-']"):
        classes = el.get("class") or []
        if not isinstance(classes, list):
            continue
        for cls in classes:
            if isinstance(cls, str) and cls.startswith("type-"):
                return cls[len("type-") :]
    return ""


class RichGistResolver(_CachedResolver):
    """Fetch the gist's HTML page to enumerate files, then each file's
    raw URL. Returns full metadata (filename, language) and supports
    multi-file gists.

    Cost: one extra request (the HTML page) plus N parallel raw fetches
    per gist; ~3-10x more bytes than the raw resolver, but the markdown
    output is fully labelled.
    """

    async def fetch(
        self, ref: GistRef, client: httpx.AsyncClient
    ) -> list[GistFile] | None:
        return await self._get_cached(ref, lambda: self._fetch(ref, client))

    async def _fetch(
        self, ref: GistRef, client: httpx.AsyncClient
    ) -> list[GistFile] | None:
        page_url = f"{_GIST_BASE}/{ref.user}/{ref.gist_id}"
        try:
            page_resp = await client.get(page_url, timeout=self.timeout_seconds)
        except httpx.RequestError as exc:
            logger.warning(
                f"Rich gist page fetch error for {ref.user}/{ref.gist_id}: {exc}"
            )
            return None
        if page_resp.status_code != 200:
            logger.warning(
                f"Rich gist page fetch failed: HTTP {page_resp.status_code} for "
                f"{ref.user}/{ref.gist_id}"
            )
            return None

        soup = BeautifulSoup(page_resp.text, "html.parser")
        metas: list[tuple[str, str, str]] = []  # (filename, raw_url, gh_lang)
        for block in soup.select(".file"):
            if not isinstance(block, Tag):
                continue
            raw_link = block.select_one('.file-actions a[href*="/raw/"]')
            if raw_link is None:
                continue
            href = raw_link.get("href")
            if not isinstance(href, str) or not href:
                continue
            filename = href.rsplit("/", 1)[-1] or "gist"
            full_url = (
                href if href.startswith("http") else f"{_GIST_BASE}{href}"
            )
            metas.append((filename, full_url, _extract_lang_from_block(block)))

        if not metas:
            logger.warning(
                f"No files found on gist page {ref.user}/{ref.gist_id}"
            )
            return None

        contents = await asyncio.gather(
            *[self._fetch_raw(client, url) for _, url, _ in metas]
        )

        files: list[GistFile] = []
        for (filename, _, gh_lang), code in zip(metas, contents):
            if not code:
                continue
            files.append(
                GistFile(
                    filename=filename,
                    lang=_infer_lang(filename, gh_lang),
                    code=code,
                )
            )
        return files or None

    async def _fetch_raw(
        self, client: httpx.AsyncClient, url: str
    ) -> str | None:
        try:
            resp = await client.get(url, timeout=self.timeout_seconds)
        except httpx.RequestError as exc:
            logger.warning(f"Rich gist raw fetch error for {url}: {exc}")
            return None
        if resp.status_code != 200:
            logger.warning(
                f"Rich gist raw fetch failed: HTTP {resp.status_code} for {url}"
            )
            return None
        return resp.text


# ---------------------------------------------------------------------------
# Service registry
# ---------------------------------------------------------------------------


_RESOLVERS: Final[dict[ResolverMode, GistResolver]] = {
    "raw": RawGistResolver(),
    "rich": RichGistResolver(),
}


@beartype
def get_resolver(mode: ResolverMode) -> GistResolver:
    return _RESOLVERS[mode]


# ---------------------------------------------------------------------------
# Top-level transform
# ---------------------------------------------------------------------------


@beartype
async def resolve_gists_in_markdown(
    markdown: str, mode: ResolverMode = "raw"
) -> str:
    """Replace each `<iframe data-iframe-id="…" srcdoc="…">` whose srcdoc
    embeds a GitHub gist with markdown code blocks fetched via the chosen
    resolver. Iframes that aren't gists, or whose fetch fails, pass
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

    resolver = get_resolver(mode)
    async with httpx.AsyncClient(
        headers={"User-Agent": "freedium/1.0"},
        follow_redirects=True,
    ) as client:
        results = await asyncio.gather(
            *[resolver.fetch(ref, client) for ref in refs]
        )
    files_by_ref: dict[GistRef, list[GistFile] | None] = dict(
        zip(refs, results)
    )

    def replace(match: re.Match[str]) -> str:
        srcdoc = html.unescape(match.group(2))
        ref = _extract_gist_ref(srcdoc)
        if not ref:
            return match.group(0)
        files = files_by_ref.get(ref)
        if not files:
            return match.group(0)
        return _render_files(files)

    return _IFRAME_RE.sub(replace, markdown)
