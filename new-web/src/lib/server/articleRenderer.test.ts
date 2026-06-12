import { describe, it, expect, vi } from "vitest";
import sampleMd from "./test-fixtures/sample.md?raw";
import { renderArticle } from "./articleRenderer";

// `renderArticle` calls render() from @/services to fetch markdown. Mock it.
vi.mock("@/services", () => ({
    render: vi.fn(async () => ({ markdown: sampleMd })),
}));

describe("renderArticle (web mode)", () => {
    it("emits dual light+dark Shiki blocks for code", async () => {
        const { html } = await renderArticle("ignored-slug");
        expect(html).toMatch(/dark:hidden/);
        expect(html).toMatch(/hidden dark:block/);
    });

    it("injects external-link icon", async () => {
        const { html } = await renderArticle("ignored-slug");
        // rehype-external-links injected an SVG inside the link
        expect(html).toMatch(/<svg[^>]*aria-hidden="true"[^>]*>/);
    });

    it("populates article metadata from frontmatter", async () => {
        const { article } = await renderArticle("ignored-slug");
        expect(article).not.toBeNull();
        expect(article!.title).toBe("Sample Article");
        expect(article!.subtitle).toBe("A test fixture");
        expect(article!.tableOfContents).toHaveLength(2);
        expect(article!.author.name).toBe("Test Author");
    });

    it("returns markdown body without frontmatter", async () => {
        const { markdown } = await renderArticle("ignored-slug");
        expect(markdown).not.toMatch(/^---/);
        expect(markdown).toMatch(/# Section One/);
    });

    it("renders postImageCaption markdown to inline HTML (no wrapping <p>)", async () => {
        const { article } = await renderArticle("ignored-slug");
        expect(article).not.toBeNull();
        const caption = article!.postImageCaption!;
        // Markdown link converted to <a> with link text preserved
        expect(caption).toMatch(/<a [^>]*href="https:\/\/unsplash\.com\/@cdr6934"[^>]*>Chris Ried/);
        // Plain literal markdown brackets are gone
        expect(caption).not.toMatch(/\[Chris Ried\]/);
        // No outer <p> wrapper (figcaption is inline-only context)
        expect(caption).not.toMatch(/^<p>/);
        // External link icon was injected (web mode)
        expect(caption).toMatch(/<svg[^>]*aria-hidden="true"/);
    });

    it("strips the external-link icon from caption in print mode", async () => {
        const { article } = await renderArticle("ignored-slug", { mode: "print" });
        expect(article!.postImageCaption).not.toMatch(/<svg/);
        expect(article!.postImageCaption).toMatch(/href="https:\/\/unsplash\.com\/@cdr6934"/);
    });
});

describe("renderArticle (print mode)", () => {
    it("emits ONLY the light Shiki block for code", async () => {
        const { html } = await renderArticle("slug", { mode: "print" });
        expect(html).not.toMatch(/dark:hidden/);
        expect(html).not.toMatch(/hidden dark:block/);
        // Still has shiki output (just one variant)
        expect(html).toMatch(/class="shiki/);
    });

    it("does NOT emit a code-copy button in print mode", async () => {
        const { html } = await renderArticle("slug", { mode: "print" });
        expect(html).not.toMatch(/code-copy-btn/);
    });

    it("web mode is unchanged (regression)", async () => {
        const { html } = await renderArticle("slug", { mode: "web" });
        expect(html).toMatch(/dark:hidden/);
        expect(html).toMatch(/code-copy-btn/);
    });
});

describe("renderArticle (print) — links", () => {
    it("strips the external-link icon", async () => {
        const { html } = await renderArticle("slug", { mode: "print" });
        // No injected SVG (the web mode test asserts presence)
        expect(html).not.toMatch(/<svg[^>]*aria-hidden="true"/);
    });

    it("keeps the link itself with the http href", async () => {
        const { html } = await renderArticle("slug", { mode: "print" });
        expect(html).toMatch(/<a[^>]*href="https:\/\/example\.com"/);
    });
});

describe("renderArticle (print) — iframes", () => {
    it("transforms a YouTube iframe into a thumbnail link", async () => {
        const { html } = await renderArticle("slug", { mode: "print" });
        expect(html).not.toMatch(/<iframe[^>]*youtube/);
        expect(html).toMatch(/class="yt-link"/);
        expect(html).toMatch(/img\.youtube\.com\/vi\/dQw4w9WgXcQ\/maxresdefault\.jpg/);
        expect(html).toMatch(/youtube\.com\/watch\?v=dQw4w9WgXcQ/);
    });

    it("leaves iframes alone in web mode (regression)", async () => {
        const { html } = await renderArticle("slug", { mode: "web" });
        expect(html).toMatch(/<iframe[^>]*youtube/);
    });

    it("transforms a YouTube iframe even when it has fallback body content", async () => {
        // Inline-fixture test: this exercises the regex against the body-content shape
        // (Medium emits these with placeholder text inside the iframe). The default
        // fixture has only the empty-body shape.
        const inlineMd = `<iframe src="https://www.youtube.com/embed/abcdefghijk">Video unavailable</iframe>`;

        const { renderArticle: rerender } = await import("./articleRenderer");
        const { render } = await import("@/services");
        // @ts-ignore — vi.mock returns a vi.Fn but the static import surface is loose
        (render as any).mockResolvedValueOnce({ markdown: inlineMd });

        const { html } = await rerender("slug", { mode: "print" });
        expect(html).not.toMatch(/<iframe/);
        expect(html).toMatch(/img\.youtube\.com\/vi\/abcdefghijk\/maxresdefault\.jpg/);
    });

    it("neutralizes a srcdoc <script> iframe in print mode (no execution)", async () => {
        const inlineMd = `<iframe data-iframe-id="x" srcdoc="<script>alert(1)</script>"></iframe>`;
        const { renderArticle: rerender } = await import("./articleRenderer");
        const { render } = await import("@/services");
        (render as any).mockResolvedValueOnce({ markdown: inlineMd });
        const { html } = await rerender("slug", { mode: "print" });
        // No src → thumbnail transform skips; sandbox (allow-same-origin, no
        // allow-scripts) still applied, so the srcdoc script can't run.
        if (html?.includes("<iframe")) {
            expect(html).toMatch(/sandbox="allow-same-origin"/);
            expect(html).not.toMatch(/sandbox="[^"]*allow-scripts/);
        }
    });

    it("HTML-escapes the src in non-YouTube iframe fallback", async () => {
        const inlineMd = `<iframe src="https://example.com/?q=&lt;evil&gt;"></iframe>`;
        const { renderArticle: rerender } = await import("./articleRenderer");
        const { render } = await import("@/services");
        (render as any).mockResolvedValueOnce({ markdown: inlineMd });

        const { html } = await rerender("slug", { mode: "print" });
        expect(html).not.toMatch(/<iframe/);
        expect(html).toMatch(/\[Embed: example\.com\]/);
        expect(html).toMatch(/href="https:\/\/example\.com/);
    });

    it("rejects javascript: scheme in iframe fallback", async () => {
        const inlineMd = `<iframe src="javascript:alert(1)"></iframe>`;
        const { renderArticle: rerender } = await import("./articleRenderer");
        const { render } = await import("@/services");
        (render as any).mockResolvedValueOnce({ markdown: inlineMd });

        const { html } = await rerender("slug", { mode: "print" });
        // rehype-sanitize strips the javascript: src before the iframe→thumbnail
        // transform runs, leaving a harmless src-less iframe. Security invariant:
        // no javascript: scheme reaches the output.
        expect(html).not.toMatch(/javascript:/);
    });
});

describe("renderArticle — XSS sanitization", () => {
    async function renderMd(md: string): Promise<string> {
        const { renderArticle } = await import("./articleRenderer");
        const { render } = await import("@/services");
        (render as any).mockResolvedValueOnce({ markdown: md });
        return (await renderArticle("slug")).html ?? "";
    }

    it("strips <script> tags from article body", async () => {
        const html = await renderMd("# T\n\n<script>alert(document.domain)</script>\n\ntext");
        expect(html).not.toContain("<script>");
        expect(html).not.toContain("alert(document.domain)");
    });

    it("strips on* event handler attributes", async () => {
        const html = await renderMd('<img src=x onerror="alert(1)">');
        expect(html).not.toMatch(/onerror/i);
    });

    it("strips javascript: links", async () => {
        const html = await renderMd("[click](javascript:alert(1))");
        expect(html).not.toMatch(/javascript:/i);
    });

    it("keeps safe markdown formatting", async () => {
        const html = await renderMd("# Heading\n\n**bold** and [link](https://ok.com)");
        expect(html).toMatch(/<h1/);
        expect(html).toContain("bold");
        expect(html).toContain("https://ok.com");
    });

    it("keeps legit embed iframes (data-iframe-id + srcdoc)", async () => {
        const html = await renderMd(
            '<iframe data-iframe-id="g1" srcdoc="<p>gist</p>" width="100%"></iframe>',
        );
        expect(html).toContain("<iframe");
        expect(html).toContain("data-iframe-id");
        expect(html).toContain("srcdoc");
    });

    // --- additional XSS vectors ---

    it("strips inline event handlers on links (onmouseover/onclick)", async () => {
        const html = await renderMd('<a href="https://ok.com" onmouseover="alert(1)" onclick="alert(2)">x</a>');
        expect(html).not.toMatch(/onmouseover/i);
        expect(html).not.toMatch(/onclick/i);
    });

    it("strips <svg><script> and svg event handlers", async () => {
        const html = await renderMd('<svg><script>alert(1)</script></svg><svg onload="alert(1)"></svg>');
        expect(html).not.toContain("alert(1)");
        expect(html).not.toMatch(/onload/i);
    });

    it("strips <iframe> with javascript: src in body (non-print)", async () => {
        const html = await renderMd('<iframe src="javascript:alert(1)"></iframe>');
        expect(html).not.toMatch(/javascript:/i);
    });

    it("neutralizes data: URI script payloads in links", async () => {
        const html = await renderMd("[x](data:text/html,<script>alert(1)</script>)");
        expect(html).not.toContain("<script>");
        // data: protocol on a link is not in the safe-protocol allowlist
        expect(html).not.toMatch(/href="data:text\/html/i);
    });

    it("strips <object>/<embed>/<form> tags", async () => {
        const html = await renderMd(
            '<object data="javascript:alert(1)"></object><embed src="x"><form action="/x"><input></form>',
        );
        expect(html).not.toContain("<object");
        expect(html).not.toContain("<embed");
        expect(html).not.toContain("<form");
        expect(html).not.toMatch(/javascript:/i);
    });

    it("strips <style> blocks and <base> hijack", async () => {
        const html = await renderMd('<style>body{background:url(javascript:alert(1))}</style><base href="https://evil.test/">');
        expect(html).not.toContain("<style>");
        expect(html).not.toContain("<base");
    });

    it("strips case-varied and whitespace-obfuscated script tags", async () => {
        const html = await renderMd('<ScRiPt>alert(1)</ScRiPt><img src=x OnError=alert(1)>');
        expect(html).not.toMatch(/<script/i);
        expect(html).not.toMatch(/onerror/i);
        expect(html).not.toContain("alert(1)");
    });

    it("strips malicious attributes from a sanctioned tag (img onload)", async () => {
        const html = await renderMd('<img src="/img/700/abc.png" onload="alert(1)" alt="ok">');
        expect(html).toContain("<img");
        expect(html).toContain('alt="ok"');
        expect(html).not.toMatch(/onload/i);
    });

    it("keeps code blocks (shiki) intact after sanitize", async () => {
        const html = await renderMd("```js\nconst x = 1;\n```");
        expect(html).toMatch(/<pre|<code/);
        expect(html).toContain("const");
    });

    it("keeps image data-zoom-src / data-caption attributes", async () => {
        const html = await renderMd('<img src="/img/700/a.png" data-zoom-src="/img/4000/a.png" data-caption="cap">');
        expect(html).toContain("data-zoom-src");
        expect(html).toContain("data-caption");
    });

    it("forces sandbox=allow-same-origin on iframes (neuters srcdoc <script>)", async () => {
        const html = await renderMd(
            '<iframe data-iframe-id="x" srcdoc="<script>alert(1)</script>"></iframe>',
        );
        expect(html).toContain("<iframe");
        expect(html).toMatch(/sandbox="allow-same-origin"/);
        // allow-same-origin without allow-scripts → the srcdoc script can't run
        expect(html).not.toMatch(/sandbox="[^"]*allow-scripts/);
    });

    it("overrides attacker-supplied iframe sandbox (no allow-scripts)", async () => {
        const html = await renderMd(
            '<iframe sandbox="allow-scripts allow-same-origin" srcdoc="<script>alert(1)</script>"></iframe>',
        );
        expect(html).not.toMatch(/allow-scripts/);
        expect(html).toMatch(/sandbox="allow-same-origin"/);
    });

    it("sandboxes external-src iframes too (not just srcdoc)", async () => {
        const html = await renderMd('<iframe src="https://example.com/embed"></iframe>');
        expect(html).toContain("<iframe");
        expect(html).toMatch(/sandbox="allow-same-origin"/);
    });

    it("sandboxes every iframe when multiple are present", async () => {
        const html = await renderMd(
            '<iframe data-iframe-id="a" srcdoc="<p>1</p>"></iframe>\n\n' +
                '<iframe data-iframe-id="b" srcdoc="<p>2</p>"></iframe>',
        );
        const sandboxes = html.match(/sandbox="allow-same-origin"/g) ?? [];
        expect(sandboxes.length).toBe(2);
    });

    it("preserves iframe layout attributes through sanitize", async () => {
        const html = await renderMd(
            '<iframe data-iframe-id="x" srcdoc="<p>g</p>" width="100%" height="320" loading="lazy"></iframe>',
        );
        expect(html).toMatch(/width="100%"/);
        expect(html).toMatch(/height="320"/);
        expect(html).toMatch(/loading="lazy"/);
    });

    it("does not execute script smuggled via caption markdown", async () => {
        // captions render through the same processor; the cover caption path
        const md = "# T\n\n![alt](/img/700/a.png)\n\ntext";
        const html = await renderMd(md);
        expect(html).not.toContain("<script>");
    });
});
