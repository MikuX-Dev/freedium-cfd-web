"""Resolve embedded gist iframes into markdown code blocks.

Used at download time so the saved .md file contains the actual code
instead of a slab of HTML the user can't read on its own.

The iframes the renderer embeds carry only a `<script src="…/USER/ID.js">`
tag in their srcdoc — GitHub injects the rendered code at runtime, so
nothing useful is parseable in the static HTML. To get real code we
extract the gist id from that script URL and fetch the gist's files
straight from `api.github.com/gists/<id>`.

Results are cached in-process with a short TTL so repeated downloads
of the same article don't hammer GitHub's unauthenticated rate limit
(60 req/hr/IP).
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
# srcdoc is non-greedy so multiple iframes don't merge.
_IFRAME_RE: Final[re.Pattern[str]] = re.compile(
    r'<iframe\b[^>]*?data-iframe-id="([^"]+)"[^>]*?srcdoc="(.*?)"[^>]*?></iframe>',
    re.DOTALL,
)

# Inside an unescaped srcdoc: <script src="https://gist.github.com/USER/HEX.js">.
# The id is the hex-only second path segment.
_GIST_SCRIPT_RE: Final[re.Pattern[str]] = re.compile(
    r'<script[^>]*\bsrc="https://gist\.github\.com/[^/"]+/([a-fA-F0-9]+)\.js"',
)

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

# GitHub language label → markdown fence label. Lowercased label is the
# fallback, but a few names need explicit overrides.
_GH_LANG_OVERRIDES: Final[dict[str, str]] = {
    "c++": "cpp",
    "c#": "csharp",
    "f#": "fsharp",
    "objective-c": "objectivec",
    "shell": "bash",
}

_GIST_CACHE_TTL_SECONDS: Final[float] = 600.0  # 10 min — gists rarely change
_GIST_REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0


@dataclass(slots=True, frozen=True)
class GistFile:
    filename: str
    lang: str
    code: str


_cache: dict[str, tuple[float, list[GistFile] | None]] = {}
_cache_lock = asyncio.Lock()
_inflight: dict[str, asyncio.Task[list[GistFile] | None]] = {}


@beartype
def _infer_lang(filename: str, gh_language: str | None = None) -> str:
    if gh_language:
        key = gh_language.strip().lower()
        if key in _GH_LANG_OVERRIDES:
            return _GH_LANG_OVERRIDES[key]
        # Whitespace and special chars don't belong in a fence label.
        if key and key.replace("-", "").replace("+", "").isalnum():
            return key
    lower = filename.lower()
    if lower == "dockerfile":
        return "dockerfile"
    if lower == "makefile":
        return "makefile"
    ext = lower.rsplit(".", 1)[-1] if "." in lower else ""
    return _EXT_TO_LANG.get(ext, "")


@beartype
def _render_files(files: list[GistFile]) -> str:
    return "\n\n".join(
        f"**{f.filename}**\n\n```{f.lang}\n{f.code}\n```" for f in files
    )


@beartype
async def _fetch_gist(
    gist_id: str, client: httpx.AsyncClient
) -> list[GistFile] | None:
    """Fetch gist files via GitHub API. Returns None on any failure
    (404, rate-limit, network) so the caller can leave the iframe intact."""
    url = f"https://api.github.com/gists/{gist_id}"
    try:
        resp = await client.get(
            url,
            headers={"Accept": "application/vnd.github+json"},
            timeout=_GIST_REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.RequestError as exc:
        logger.warning(f"Gist fetch network error for {gist_id}: {exc}")
        return None
    if resp.status_code != 200:
        logger.warning(
            f"Gist fetch failed for {gist_id}: HTTP {resp.status_code}"
        )
        return None
    try:
        data = resp.json()
    except ValueError as exc:
        logger.warning(f"Gist {gist_id} returned non-JSON: {exc}")
        return None

    files: list[GistFile] = []
    for fname, fdata in (data.get("files") or {}).items():
        if not isinstance(fdata, dict):
            continue
        # GitHub truncates files >1MB and stores a partial in `content`. We
        # fall back to fetching `raw_url` when truncated to recover the rest.
        content = fdata.get("content") or ""
        if fdata.get("truncated") and (raw_url := fdata.get("raw_url")):
            try:
                raw_resp = await client.get(
                    raw_url, timeout=_GIST_REQUEST_TIMEOUT_SECONDS
                )
                if raw_resp.status_code == 200:
                    content = raw_resp.text
            except httpx.RequestError as exc:
                logger.warning(
                    f"Gist {gist_id} raw fetch failed for {fname}: {exc}"
                )
        if not content:
            continue
        files.append(
            GistFile(
                filename=fname,
                lang=_infer_lang(fname, fdata.get("language")),
                code=content,
            )
        )
    return files or None


@beartype
async def _get_gist_cached(
    gist_id: str, client: httpx.AsyncClient
) -> list[GistFile] | None:
    """Return cached gist files if fresh, else fetch (deduping concurrent
    requests for the same id)."""
    now = time.monotonic()
    async with _cache_lock:
        cached = _cache.get(gist_id)
        if cached and now - cached[0] < _GIST_CACHE_TTL_SECONDS:
            return cached[1]
        task = _inflight.get(gist_id)
        is_originator = task is None
        if is_originator:
            task = asyncio.create_task(_fetch_gist(gist_id, client))
            _inflight[gist_id] = task
    assert task is not None
    files = await task
    if is_originator:
        async with _cache_lock:
            _inflight.pop(gist_id, None)
            _cache[gist_id] = (time.monotonic(), files)
    return files


@beartype
def _extract_gist_id(srcdoc_unescaped: str) -> str | None:
    m = _GIST_SCRIPT_RE.search(srcdoc_unescaped)
    return m.group(1) if m else None


@beartype
async def resolve_gists_in_markdown(markdown: str) -> str:
    """Replace each `<iframe data-iframe-id="…" srcdoc="…">` whose srcdoc
    embeds a GitHub gist with markdown code fences for every file in the
    gist. Iframes that aren't gists, or whose fetch fails, pass through
    untouched.
    """
    # Pass 1: collect distinct gist ids to fetch
    gist_ids: list[str] = []
    seen: set[str] = set()
    for m in _IFRAME_RE.finditer(markdown):
        srcdoc = html.unescape(m.group(2))
        gid = _extract_gist_id(srcdoc)
        if gid and gid not in seen:
            seen.add(gid)
            gist_ids.append(gid)

    if not gist_ids:
        return markdown

    # Fetch all in parallel through one connection pool
    async with httpx.AsyncClient(
        headers={"User-Agent": "freedium/1.0"}
    ) as client:
        results = await asyncio.gather(
            *[_get_gist_cached(gid, client) for gid in gist_ids]
        )
    files_by_id: dict[str, list[GistFile] | None] = dict(zip(gist_ids, results))

    # Pass 2: substitute iframes whose gist resolved successfully
    def replace(match: re.Match[str]) -> str:
        srcdoc = html.unescape(match.group(2))
        gid = _extract_gist_id(srcdoc)
        if not gid:
            return match.group(0)
        files = files_by_id.get(gid)
        if not files:
            return match.group(0)
        return _render_files(files)

    return _IFRAME_RE.sub(replace, markdown)
