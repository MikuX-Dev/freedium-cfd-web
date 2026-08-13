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
import re
from collections.abc import Callable, Coroutine
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Any, Final, Literal, Protocol, runtime_checkable

import httpx
from beartype import beartype
from bs4 import BeautifulSoup, Tag
from loguru import logger

from freedium_library.utils.cache.redis_ttl import RedisTTLCache

# Applied to a parsed <script src="…"> value, not to raw HTML.
_GIST_SRC_RE: Final[re.Pattern[str]] = re.compile(
    r"^https://gist\.github\.com/([^/]+)/([a-fA-F0-9]+)\.js$",
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


@dataclass(slots=True, frozen=True)
class _IframeSpan:
    """One <iframe> element located in the source: its exact character range
    and its already-decoded `srcdoc`."""

    start: int
    end: int
    srcdoc: str | None


class _IframeFinder(HTMLParser):
    """Collects the source span of every <iframe> element.

    The input is markdown with embedded HTML, so it can't be parsed and
    re-serialised — that would escape and reflow the surrounding markdown.
    Instead this records exact character offsets, letting the caller splice
    replacements in and leave everything else byte-for-byte intact.

    Using a real parser means attribute order, quoting and entity escaping are
    handled for us, and attribute values arrive decoded.
    """

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self._source = source
        # Absolute offset of the start of each line, for getpos() → index.
        self._line_starts: list[int] = [0]
        for line in source.splitlines(keepends=True):
            self._line_starts.append(self._line_starts[-1] + len(line))
        self._open_start: int | None = None
        self._open_srcdoc: str | None = None
        self.spans: list[_IframeSpan] = []

    def _offset(self) -> int:
        line, col = self.getpos()
        return self._line_starts[line - 1] + col

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "iframe" or self._open_start is not None:
            return
        self._open_start = self._offset()
        self._open_srcdoc = next(
            (v for k, v in attrs if k == "srcdoc" and v is not None), None
        )

    def handle_endtag(self, tag: str) -> None:
        if tag != "iframe" or self._open_start is None:
            return
        # getpos() points at the '<' of "</iframe"; the element ends after the
        # next '>', which also covers spellings like "</iframe >".
        close = self._source.find(">", self._offset())
        end = len(self._source) if close == -1 else close + 1
        self.spans.append(
            _IframeSpan(start=self._open_start, end=end, srcdoc=self._open_srcdoc)
        )
        self._open_start = None
        self._open_srcdoc = None


@beartype
def _find_iframes(source: str) -> list[_IframeSpan]:
    """Every <iframe> element in `source`, with exact spans. Malformed HTML
    yields no spans rather than raising — a broken embed must not fail the
    whole export."""
    finder = _IframeFinder(source)
    try:
        finder.feed(source)
        finder.close()
    except Exception as exc:  # noqa: BLE001 — never break an export over markup
        logger.debug(f"gist resolver: iframe parse failed ({exc!r})")
        return []
    return finder.spans


@beartype
def _extract_gist_ref(srcdoc: str) -> GistRef | None:
    """The gist a srcdoc embeds, or None if it embeds something else.

    The srcdoc is a small HTML document; walk its <script> tags and match the
    gist URL on the parsed `src` value.
    """
    for script in BeautifulSoup(srcdoc, "html.parser").find_all("script"):
        src = script.get("src")
        if not isinstance(src, str):
            continue
        m = _GIST_SRC_RE.match(src)
        if m:
            return GistRef(user=m.group(1), gist_id=m.group(2))
    return None


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

# Shared across resolver instances, uvicorn workers and backend replicas.
# Redis expires entries natively, so this can't grow without bound the way the
# old process-local dict did.
_gist_cache: Final[RedisTTLCache] = RedisTTLCache(
    namespace="gist", ttl_seconds=int(_DEFAULT_TTL_SECONDS)
)


@dataclass(slots=True)
class _CachedResolver:
    """Redis TTL cache + in-flight dedup. Subclasses implement `_do_fetch`
    and call `_get_cached` from their public `fetch`."""

    ttl_seconds: float = _DEFAULT_TTL_SECONDS
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS

    async def _get_cached(
        self,
        ref: GistRef,
        fetcher: Callable[
            [], Coroutine[Any, Any, list[GistFile] | None]
        ],
    ) -> list[GistFile] | None:
        async def fetch_as_dicts() -> list[dict[str, str]] | None:
            files = await fetcher()
            return None if files is None else [asdict(f) for f in files]

        cached = await _gist_cache.get_or_fetch(
            f"{ref.user}/{ref.gist_id}", fetch_as_dicts
        )
        return None if cached is None else [GistFile(**d) for d in cached]


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
    # Locate every iframe once, pairing each gist span with its ref so the
    # splice below needs no re-parsing.
    spans = _find_iframes(markdown)
    gist_spans: list[tuple[_IframeSpan, GistRef]] = []
    refs: list[GistRef] = []
    seen: set[GistRef] = set()

    for span in spans:
        if span.srcdoc is None:
            continue
        ref = _extract_gist_ref(span.srcdoc)
        if not ref:
            continue
        gist_spans.append((span, ref))
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)

    if not refs:
        # Distinguish "no iframes at all" from "iframes present but none looked
        # like a gist" — the latter is how a Medium markup change would surface,
        # and it used to be indistinguishable from the normal no-op.
        if spans:
            logger.debug(
                f"gist resolver: {len(spans)} iframe(s) found, none embedded a gist"
            )
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

    # Splice replacements in by offset, left to right. Everything outside the
    # replaced spans — including the surrounding markdown — is copied verbatim.
    out: list[str] = []
    cursor = 0
    for span, ref in gist_spans:
        files = files_by_ref.get(ref)
        if not files:
            continue  # fetch failed — leave the original embed in place
        out.append(markdown[cursor : span.start])
        out.append(_render_files(files))
        cursor = span.end
    out.append(markdown[cursor:])
    return "".join(out)
