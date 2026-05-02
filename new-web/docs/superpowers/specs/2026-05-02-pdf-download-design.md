# PDF Download — Design Spec

**Date:** 2026-05-02
**Branch:** `feat/home-redesign`
**Status:** Approved, awaiting implementation plan

## Goal

Wire the existing "Download as PDF" dropdown item in the article page so it produces a PDF that closely mirrors the web rendering. PDF generation uses WeasyPrint server-side, fed by a single shared markdown→HTML rendering pipeline that powers both the web view and the print view.

## Non-goals

- Vimeo / Twitter / CodePen / generic OpenGraph iframe thumbnails. Only YouTube is treated specially; everything else falls back to a labeled link.
- Custom font bundling. System fonts (Georgia, Helvetica) via fontconfig only.
- Async / queued generation. Sync HTTP request; the SvelteKit Remote Function awaits the Python response inline.
- PDF/A or accessibility tagging.
- Per-user PDF style customization (paper size, cover layout).
- Caching of generated PDFs.
- Headless-browser screenshot fallback for arbitrary embeds.

## Architecture

```
Browser:  click "Download as PDF"
   │  await generatePdf(slug)                      ← SvelteKit Remote Function (typed RPC)
   ▼
SvelteKit (server, .remote.ts boundary)
   │  ── renderArticle(slug, {mode:"print"})       ← shared in-process module
   │  ── buildPrintDocument(article, html)         ← inlines printStyles.css, builds <html>
   │  ── fetch POST → ${PDF_SERVICE_URL}/internal/pdf
   │       headers: X-Internal-Secret
   │       body: { html, filename }
   │  ── Python: prefetch images → inline → WeasyPrint → PDF bytes
   │  ── return { bytes: Uint8Array, filename: string }
   ▼
Browser (client)
   │  ── new Blob([bytes], { type: 'application/pdf' })
   │  ── URL.createObjectURL → synthetic <a download> click → revokeObjectURL
   ▼
Native browser download
```

**Why SvelteKit-entry over Python-entry:**

- HTML never leaves the SvelteKit Node process for the render→print transition (one in-process function call instead of an HTTP loopback).
- Python becomes a pure HTML→PDF microservice. No URL-fetching, no markdown awareness, no SvelteKit-address coupling.
- No need to expose a `/print/[slug]` route; `/article/[slug]/pdf` (implicit via Remote Function) is the only user-facing PDF surface.
- Same-origin: no CORS handling for the download response.

**Why Remote Functions over `+server.ts`:**

- Typed call from client, validated input via `valibot`.
- Co-located with renderer in `$lib/server`.
- Eliminates fetch glue at the call site.
- Tradeoff: binary returned through devalue serialization (Uint8Array). PDF lands fully in memory on the client before the download starts. Fine for 1–3 MB PDFs typical of articles. If 20 MB PDFs become routine, switch to a streaming `+server.ts` endpoint as a follow-up.

## Components

### 1. Shared SvelteKit renderer

**File layout:**

```
src/lib/server/
  articleRenderer.ts      — single export: renderArticle(slug, { mode })
  printDocument.ts        — buildPrintDocument(article, contentHtml) → full HTML page
  printStyles.css         — imported as string via Vite ?raw, inlined into <style>
```

**`articleRenderer.ts` public surface:**

```ts
export type RenderMode = 'web' | 'print';

export interface ArticleMetadata {
  title: string;
  subtitle?: string;
  author: { name: string; avatar: string; role: string };
  date: string;
  postImage: string | null;
  postImageZoom: string | null;
  postImageCaption?: string;
  url: string | null;
  tableOfContents: Array<{ id: string; title: string }>;
}

export interface RenderResult {
  html: string;          // article body HTML, no <html>/<head> wrapper
  markdown: string;      // raw markdown, frontmatter stripped
  article: ArticleMetadata | null;
}

export async function renderArticle(
  slug: string,
  options?: { mode?: RenderMode }
): Promise<RenderResult>;
```

Internally: existing logic from `+page.server.ts` (call `render()`, parse frontmatter, build metadata, run unified pipeline) plus mode-aware rehype configuration.

**Mode branching:**

| Step | `mode: 'web'` (default, current behavior) | `mode: 'print'` |
|---|---|---|
| `rehypeHighlight` (Shiki) | dual `github-light` + `github-dark`, wrapped with `dark:hidden` / `hidden dark:block`, copy button overlay | single `github-light`, no copy button |
| `rehypeExternalLinks` content | inject heroicons `arrow-top-right-on-square` SVG | none; **new** `rehypePrintifyLinks` appends ` (https://…)` after each external link |
| `<iframe>` handling | passthrough (lazy-loaded client-side) | **new** `rehypeIframeToThumbnail`: YouTube → `<a class="yt-link" href="watch-url"><img class="yt-thumb"/><span class="yt-play">▶</span></a>`; non-YouTube → `<a>[Embed: hostname]</a>` |
| `rehypeSlug` | applied | applied (TOC links resolve via `target-counter`) |
| `remarkRehype` `allowDangerousHtml` | `true` | `true` |

**`+page.server.ts` after extraction shrinks to ~25 lines:**

```ts
import { renderArticle } from '$lib/server/articleRenderer';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
  try {
    const { html, markdown, article } = await renderArticle(params.slug);
    return { slug: params.slug, loading: false, content: html, markdown, article, error: null };
  } catch (err) {
    return { slug: params.slug, loading: false, content: null, markdown: null,
             article: null, error: mapRenderError(err) };
  }
};
```

**`printDocument.ts`:**

```ts
import printStyles from './printStyles.css?raw';
import type { ArticleMetadata } from './articleRenderer';

export function buildPrintDocument(article: ArticleMetadata, contentHtml: string): string;
```

Returns a complete `<!doctype html>` document with:
- Inlined `<style>` containing `printStyles`.
- Cover page section (only if `article.postImage`).
- TOC section (only if `article.tableOfContents.length > 0`); each entry `<a href="#id">Title <span class="page"></span></a>`.
- Article body wrapped in `<article class="prose-print" data-title="…">`.

### 2. SvelteKit Remote Function

**`src/lib/article.remote.ts`:**

```ts
import { command } from '$app/server';
import * as v from 'valibot';
import { renderArticle } from '$lib/server/articleRenderer';
import { buildPrintDocument } from '$lib/server/printDocument';
import { PDF_SERVICE_URL, PDF_SERVICE_SECRET } from '$env/static/private';

export const generatePdf = command(v.string(), async (slug) => {
  const { html, article } = await renderArticle(slug, { mode: 'print' });
  if (!article) throw new Error('Article not found');

  const printHtml = buildPrintDocument(article, html);
  const filename = slugify(article.title) + '.pdf';

  const res = await fetch(`${PDF_SERVICE_URL}/internal/pdf`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-internal-secret': PDF_SERVICE_SECRET
    },
    body: JSON.stringify({ html: printHtml, filename })
  });
  if (!res.ok) throw new Error(`PDF service ${res.status}`);

  return {
    bytes: new Uint8Array(await res.arrayBuffer()),
    filename
  };
});
```

**Client-side handler in `ArticleActions.svelte`:**

```ts
async function downloadPdf() {
  const { bytes, filename } = await generatePdf(slug);
  const blob = new Blob([bytes], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
```

Wire `downloadPdf` to the existing "Download as PDF" `DropdownMenu.Item`.

### 3. Python `/internal/pdf` endpoint

**File:** `freedium-library/src/freedium_library/api/handlers/pdf.py`

```python
class PdfRequest(BaseModel):
    html: str
    filename: str

@beartype
async def generate_pdf(
    req: PdfRequest,
    _: None = Depends(require_internal_secret),
) -> Response:
    inlined = await inline_images(req.html)
    pdf_bytes = render_pdf(inlined)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{req.filename}"'},
    )
```

Mounted under `/internal/pdf` (POST). Sibling pattern to existing `download.py`. Registered via `register_pdf_router(router)` in the API root.

**Auth — shared-secret header:**

```python
def require_internal_secret(x_internal_secret: str = Header(...)) -> None:
    if x_internal_secret != settings.pdf_internal_secret:
        raise HTTPException(403, "Forbidden")
```

`pdf_internal_secret` joins the existing settings/config layer.

**Image pre-fetch — `inline_images(html: str) -> str`:**

1. Parse with `lxml.html`.
2. Collect unique URLs from `<img src>` and `<source srcset>` (split srcset on commas/whitespace).
3. Concurrent fetch via shared `httpx.AsyncClient`:
   - `asyncio.Semaphore(16)` parallelism cap.
   - `httpx.Timeout(connect=3, read=8)` per image.
   - Read up to `MAX_IMAGE_BYTES = 5_000_000`; abort on exceed.
4. Encode each successful response as `data:<content-type>;base64,<…>`.
5. Substitute in the parsed tree, serialize back.
6. Failures (404, timeout, oversize, network error) → 1×1 transparent SVG data URI placeholder + warning log via `loguru`. Never raise.

Typical 10-image article: ~1–2 s wall-clock dominated by slowest image, vs ~10–20 s if WeasyPrint fetched serially.

**`render_pdf(html: str) -> bytes`:**

```python
from weasyprint import HTML
def render_pdf(html: str) -> bytes:
    return HTML(string=html).write_pdf()
```

`base_url` not needed — every asset is an inline `data:` URI. WeasyPrint does zero network I/O at this stage.

**Failure modes:**

| Cause | Status | Behavior |
|---|---|---|
| Missing/wrong `X-Internal-Secret` | 403 | Reject before parsing |
| HTML parse fails | 400 | Surface message to SvelteKit |
| All images fail | 200 | PDF generates with placeholders, warnings logged |
| Single image timeout | 200 | That image becomes placeholder, rest succeed |
| WeasyPrint exception | 502 | Logged with traceback, opaque error to client |

### 4. Print stylesheet (`printStyles.css`)

Drives all page-layout decisions through CSS Paged Media (which WeasyPrint implements thoroughly).

**`@page` rules:**

```css
@page {
  size: A4 portrait;
  margin: 2cm 2cm 2.5cm 2cm;
  @top-center {
    content: string(article-title);
    font: 9pt 'Helvetica', sans-serif;
    color: #666;
    border-bottom: 0.5pt solid #ddd;
    padding-bottom: 4mm;
  }
  @bottom-left {
    content: 'Generated by Freedium';
    font: 8pt 'Helvetica', sans-serif; color: #888;
  }
  @bottom-right {
    content: 'Page ' counter(page) ' of ' counter(pages);
    font: 8pt 'Helvetica', sans-serif; color: #888;
  }
}
@page cover, @page :first {
  @top-center, @bottom-left, @bottom-right { content: none; }
}
```

**`string-set` for the running header:**

```css
.prose-print { string-set: article-title attr(data-title); }
```

`<article class="prose-print" data-title="…">` carries the title; WeasyPrint reads it once, header injects on every body page.

**Cover page:**

```css
.cover { page: cover; page-break-after: always; height: 297mm; }
.cover-image { width: 100%; height: 50vh; object-fit: cover; }
.cover-content { padding: 3cm 2cm 2cm; }
.cover-title    { font: bold 32pt/1.15 Georgia, serif; margin: 0 0 0.5cm; color: #111; }
.cover-subtitle { font: 16pt/1.3 Georgia, serif;       margin: 0 0 1cm;   color: #444; }
.cover-meta     { margin-top: 2cm; font: 11pt 'Helvetica', sans-serif; }
```

**TOC with auto page numbers:**

```css
.toc { page-break-after: always; }
.toc h2 { font: bold 24pt Georgia, serif; margin: 0 0 1cm; }
.toc ol { list-style: none; padding: 0; }
.toc li { margin: 0 0 0.4cm; }
.toc a {
  text-decoration: none; color: #111;
  display: flex; justify-content: space-between;
}
.toc a::after {
  content: target-counter(attr(href), page);
  color: #666;
}
```

`target-counter(attr(href), page)` — WeasyPrint follows the in-doc anchor and prints the destination page number.

**Prose body, conservative pagination:**

```css
.prose-print {
  font: 11pt/1.55 Georgia, serif;
  color: #1a1a1a;
}
.prose-print h1 { font-size: 22pt; margin: 1cm 0 0.4cm;  page-break-after: avoid; }
.prose-print h2 { font-size: 16pt; margin: 0.8cm 0 0.3cm; page-break-after: avoid; }
.prose-print h3 { font-size: 13pt; margin: 0.6cm 0 0.2cm; page-break-after: avoid; }
.prose-print p  { margin: 0 0 0.4cm; orphans: 3; widows: 3; }
.prose-print img        { max-width: 100%; height: auto; page-break-inside: avoid; }
.prose-print figure     { margin: 0.5cm 0; }
.prose-print figcaption { font: italic 9pt 'Helvetica', sans-serif; color: #666; text-align: center; }
.prose-print blockquote {
  margin: 0.5cm 0; padding: 0.3cm 0.5cm;
  border-left: 3pt solid #ddd; background: #f7f7f7;
  page-break-inside: avoid;
}
.prose-print pre {
  background: #f6f8fa; border: 0.5pt solid #e0e0e0; border-radius: 4pt;
  padding: 0.3cm; font: 9pt/1.5 'Consolas', monospace;
  white-space: pre-wrap; word-wrap: break-word;
  page-break-inside: avoid;
}
.prose-print pre code { background: transparent; padding: 0; }
.prose-print code {
  font: 0.92em 'Consolas', monospace;
  background: #f4f4f4; padding: 0.05em 0.3em; border-radius: 2pt;
}
.prose-print table { width: 100%; border-collapse: collapse; margin: 0.5cm 0; font-size: 10pt; }
.prose-print th, .prose-print td { border: 0.5pt solid #ccc; padding: 0.2cm; text-align: left; }
.prose-print th { background: #f0f0f0; font-weight: bold; }
```

**External link URLs after the link text:**

```css
.prose-print a { color: #0066cc; text-decoration: none; }
.prose-print a[href^="http"]::after {
  content: " (" attr(href) ")";
  font-size: 0.85em; color: #777;
  word-break: break-all;
}
.prose-print a[href^="#"]::after,
.prose-print a.yt-link::after { content: none; }
```

**YouTube thumbnail:**

```css
.yt-link {
  display: block; position: relative;
  margin: 0.5cm 0; text-decoration: none;
  page-break-inside: avoid;
}
.yt-thumb { width: 100%; border-radius: 4pt; display: block; }
.yt-play {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(0,0,0,0.7); color: white;
  font-size: 20pt; padding: 0.2cm 0.6cm;
  border-radius: 50%;
}
```

**Font choice rationale.** Georgia (serif) and Helvetica (sans) are nearly universal across Linux/macOS/Windows fontconfig, so PDFs render predictably without bundling fonts. If a host lacks them, fontconfig substitutes — degrades gracefully.

**WeasyPrint compatibility note.** Everything uses CSS Paged Media + plain block/inline. No flexbox/grid in load-bearing positions (`.cover-meta` and `.toc a` flex usages are presentational only).

## Dependencies

**Python (`pyproject.toml`):**
```toml
weasyprint = "^62.0"
lxml = "^5.0"
```

**System (Dockerfile / devcontainer):**
```
libpango-1.0-0
libcairo2
libgdk-pixbuf-2.0-0
libffi-dev
fontconfig
libxml2
libxslt1.1
```

**Frontend:** no new npm packages. Remote Functions and `valibot` already in the SvelteKit-supported set.

If on a SvelteKit version where Remote Functions are still flagged experimental, enable in `svelte.config.js`:
```js
kit: { experimental: { remoteFunctions: true } }
```
Implementation step will check the installed SvelteKit version and toggle the flag if needed.

**Env vars:**

- `PDF_SERVICE_URL` — Python service base URL (e.g. `http://localhost:7080` in dev).
- `PDF_SERVICE_SECRET` — shared secret for `X-Internal-Secret` header.

Add corresponding settings on the Python side: `pdf_internal_secret`.

## Testing

**SvelteKit (Vitest):**
- `articleRenderer.test.ts` — fixtures for both modes; assert Shiki dual vs single, link icon presence, iframe transformation, common metadata.
- `printDocument.test.ts` — snapshot full HTML; assert cover/TOC conditional rendering and `data-title` attribute.

**Python (pytest):**
- `test_inline_images.py` — mocked httpx for success, 404, timeout, oversize cases; concurrent-fetch verification.
- `test_pdf_endpoint.py` — TestClient for auth, body validation, `%PDF-` magic bytes, `Content-Disposition`.
- `test_pdf_e2e.py` — fixture HTML through full handler; `pypdf` to verify page count, title text, footer text.

**End-to-end (Playwright via MCP):**
- Click "Download as PDF" on a real article in dev; assert filename and size; extract text from PDF and verify title appears.

## Acceptance criteria

1. Click "Download as PDF" on any article → PDF downloads with the correct filename within 10 s for typical articles.
2. Cover page shows hero image, title, subtitle, author, date when `postImage` exists.
3. Body pages show running header (article title) and running footer (`Page N of M` + Freedium attribution).
4. TOC page renders with linked entries showing correct destination page numbers.
5. Code blocks render with light Shiki highlighting only; no dark variant ghost; no copy button.
6. External links print their URL after the link text in muted gray.
7. YouTube embeds render as thumbnail with ▶ overlay; clicking opens YouTube in PDF viewers that support links.
8. Other iframes render as labeled link.
9. Existing markdown download is unaffected.
10. Existing article web view is visually unchanged after the renderer extraction.

## Risks

- WeasyPrint system deps must be installed in the dev devcontainer; verify before implementation, add `apt-get` block if missing.
- WeasyPrint flexbox support is partial. `.cover-meta` and `.toc a` flex are presentational; eyeball the first generated PDF.
- Large inline SVGs can blow memory; the 5 MB cap mitigates.
- Long unbreakable code tokens (long URLs, hashes) may overflow page width; `pre-wrap` + `word-wrap: break-word` handles most cases. Add `hyphens: auto` later if reported.
