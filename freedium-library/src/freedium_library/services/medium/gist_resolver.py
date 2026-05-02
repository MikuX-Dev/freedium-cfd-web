"""Resolve embedded gist iframes into markdown code blocks.

Used at download time so the saved .md file contains the actual code
instead of a slab of HTML the user can't read on its own. Pure transform:
takes the rendered markdown (with `<iframe ... srcdoc="...">` blocks
already embedded by the renderer) and substitutes matching iframes with
markdown code fences. Non-gist iframes are left intact.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Final

from beartype import beartype
from bs4 import BeautifulSoup, Tag

# Match <iframe ... data-iframe-id="..." ... srcdoc="..." ... ></iframe>.
# srcdoc is non-greedy so multiple iframes on one line are handled correctly.
_IFRAME_RE: Final[re.Pattern[str]] = re.compile(
    r'<iframe\b[^>]*?data-iframe-id="([^"]+)"[^>]*?srcdoc="(.*?)"[^>]*?></iframe>',
    re.DOTALL,
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


@dataclass(slots=True, frozen=True)
class GistFile:
    filename: str
    lang: str
    code: str


@beartype
def _infer_lang(filename: str) -> str:
    lower = filename.lower()
    if lower == "dockerfile":
        return "dockerfile"
    if lower == "makefile":
        return "makefile"
    ext = lower.rsplit(".", 1)[-1] if "." in lower else ""
    return _EXT_TO_LANG.get(ext, "")


@beartype
def _extract_filename(file_el: Tag) -> str:
    meta = file_el.select_one(".gist-meta")
    if meta is None:
        return "gist"
    for link in meta.select("a"):
        text = (link.get_text() or "").strip()
        if re.search(r"\.[A-Za-z0-9]+$", text):
            return text
        href = link.get("href") or ""
        if isinstance(href, str) and "gist.githubusercontent.com" in href:
            tail = href.rsplit("/", 1)[-1]
            if tail:
                return tail
    return "gist"


@beartype
def _extract_code(file_el: Tag) -> str:
    """Concatenate the file's line cells. .blob-code-inner holds source
    text with GitHub's syntax-highlight spans; get_text() strips spans
    and preserves the literal text. One row per source line."""
    cells = file_el.select("td.blob-code-inner")
    if not cells:
        return ""
    return "\n".join((cell.get_text() or "").rstrip("\n") for cell in cells)


@beartype
def _extract_files(srcdoc_html: str) -> list[GistFile]:
    soup = BeautifulSoup(srcdoc_html, "html.parser")
    files: list[GistFile] = []
    for el in soup.select(".gist-file"):
        if not isinstance(el, Tag):
            continue
        code = _extract_code(el)
        if not code:
            continue
        filename = _extract_filename(el)
        files.append(
            GistFile(filename=filename, lang=_infer_lang(filename), code=code)
        )
    return files


@beartype
def _render_files(files: list[GistFile]) -> str:
    parts: list[str] = []
    for f in files:
        parts.append(f"**{f.filename}**\n\n```{f.lang}\n{f.code}\n```")
    return "\n\n".join(parts)


@beartype
def resolve_gists_in_markdown(markdown: str) -> str:
    """Replace each `<iframe data-iframe-id="…" srcdoc="…">` whose srcdoc
    contains a gist embed with markdown code fences for each file inside.

    Iframes whose srcdoc isn't a gist (YouTube, Twitter, missing) are left
    untouched — the original iframe HTML stays in the output.
    """

    def replace(match: re.Match[str]) -> str:
        srcdoc_escaped = match.group(2)
        srcdoc = html.unescape(srcdoc_escaped)
        files = _extract_files(srcdoc)
        if not files:
            return match.group(0)
        return _render_files(files)

    return _IFRAME_RE.sub(replace, markdown)
