"""Resolve embedded gist iframes into markdown code blocks.

Used at download time so the saved .md file contains the actual code
instead of a slab of HTML the user can't read on its own.

The iframes the renderer embeds carry only a `<script src="…/USER/ID.js">`
tag in their srcdoc — GitHub injects the rendered code at runtime, so
nothing useful is parseable in the static HTML. To resolve gists we hit
`gist.github.com` URLs directly (not the rate-limited api.github.com):

  1. Fetch the gist's HTML page to enumerate every file and grab each
     file's "view raw" link, which embeds the filename and commit SHA.
  2. Fetch each raw URL — `gist.github.com/USER/ID/raw/SHA/FILENAME`
     resolves to the canonical raw content with original whitespace
     preserved (the rendered HTML mangles indentation).

Results are cached in-process with a short TTL so repeated downloads of
the same article don't pile on extra requests.
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

# GitHub's `class="type-…"` label → markdown fence label.
_GH_LANG_OVERRIDES: Final[dict[str, str]] = {
    "c++": "cpp",
    "c#": "csharp",
    "f#": "fsharp",
    "objective-c": "objectivec",
    "shell": "bash",
}

_GIST_BASE: Final[str] = "https://gist.github.com"
_GIST_CACHE_TTL_SECONDS: Final[float] = 600.0
_GIST_REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0


@dataclass(slots=True, frozen=True)
class GistRef:
    user: str
    gist_id: str


@dataclass(slots=True, frozen=True)
class GistFile:
    filename: str
    lang: str
    code: str


_cache: dict[GistRef, tuple[float, list[GistFile] | None]] = {}
_cache_lock = asyncio.Lock()
_inflight: dict[GistRef, asyncio.Task[list[GistFile] | None]] = {}


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


@beartype
def _render_files(files: list[GistFile]) -> str:
    return "\n\n".join(
        f"**{f.filename}**\n\n```{f.lang}\n{f.code}\n```" for f in files
    )


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


@beartype
async def _fetch_raw(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(url, timeout=_GIST_REQUEST_TIMEOUT_SECONDS)
    except httpx.RequestError as exc:
        logger.warning(f"Gist raw fetch error for {url}: {exc}")
        return None
    if resp.status_code != 200:
        logger.warning(f"Gist raw fetch failed: HTTP {resp.status_code} for {url}")
        return None
    return resp.text


@beartype
async def _fetch_gist(
    ref: GistRef, client: httpx.AsyncClient
) -> list[GistFile] | None:
    """Resolve a gist's files via gist.github.com URLs only.

    Step 1: GET the HTML page, enumerate files, capture each file's raw
    URL (which carries the commit SHA + filename) and language hint.
    Step 2: GET each raw URL in parallel for the canonical content.

    Returns None on any non-recoverable failure (network, missing page,
    empty file list) so the caller can leave the iframe intact.
    """
    page_url = f"{_GIST_BASE}/{ref.user}/{ref.gist_id}"
    try:
        page_resp = await client.get(
            page_url, timeout=_GIST_REQUEST_TIMEOUT_SECONDS
        )
    except httpx.RequestError as exc:
        logger.warning(
            f"Gist page fetch error for {ref.user}/{ref.gist_id}: {exc}"
        )
        return None
    if page_resp.status_code != 200:
        logger.warning(
            f"Gist page fetch failed: HTTP {page_resp.status_code} for "
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
        full_url = href if href.startswith("http") else f"{_GIST_BASE}{href}"
        metas.append((filename, full_url, _extract_lang_from_block(block)))

    if not metas:
        logger.warning(f"No files found on gist page {ref.user}/{ref.gist_id}")
        return None

    contents = await asyncio.gather(
        *[_fetch_raw(client, url) for _, url, _ in metas]
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


@beartype
async def _get_gist_cached(
    ref: GistRef, client: httpx.AsyncClient
) -> list[GistFile] | None:
    now = time.monotonic()
    async with _cache_lock:
        cached = _cache.get(ref)
        if cached and now - cached[0] < _GIST_CACHE_TTL_SECONDS:
            return cached[1]
        task = _inflight.get(ref)
        is_originator = task is None
        if is_originator:
            task = asyncio.create_task(_fetch_gist(ref, client))
            _inflight[ref] = task
    assert task is not None
    files = await task
    if is_originator:
        async with _cache_lock:
            _inflight.pop(ref, None)
            _cache[ref] = (time.monotonic(), files)
    return files


@beartype
def _extract_gist_ref(srcdoc_unescaped: str) -> GistRef | None:
    m = _GIST_SCRIPT_RE.search(srcdoc_unescaped)
    if not m:
        return None
    return GistRef(user=m.group(1), gist_id=m.group(2))


@beartype
async def resolve_gists_in_markdown(markdown: str) -> str:
    """Replace each `<iframe data-iframe-id="…" srcdoc="…">` whose srcdoc
    embeds a GitHub gist with markdown code fences for every file in the
    gist. Iframes that aren't gists, or whose fetch fails, pass through
    untouched.
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
            *[_get_gist_cached(ref, client) for ref in refs]
        )
    files_by_ref: dict[GistRef, list[GistFile] | None] = dict(zip(refs, results))

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
