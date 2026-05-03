import { describe, it, expect } from "vitest";
import { buildPrintDocument } from "./printDocument";
import type { ArticleMetadata } from "./articleRenderer";

const baseArticle: ArticleMetadata = {
    title: "Test Article",
    subtitle: "A subtitle",
    author: { name: "Author Name", avatar: "https://x/a.png", role: "Writer" },
    date: "2026-05-02T00:00:00Z",
    postImage: null,
    postImageZoom: null,
    url: "https://example.com",
    tableOfContents: [],
};

describe("buildPrintDocument", () => {
    it("returns a complete HTML document", () => {
        const html = buildPrintDocument(baseArticle, "<p>Body</p>");
        expect(html).toMatch(/^<!doctype html>/i);
        expect(html).toMatch(/<html[^>]*>/);
        expect(html).toMatch(/<\/html>/);
        expect(html).toMatch(/<style>/);
        expect(html).toMatch(/<\/style>/);
        expect(html).toMatch(/<p>Body<\/p>/);
    });

    it("sets data-title on the prose article element", () => {
        const html = buildPrintDocument(baseArticle, "<p>x</p>");
        expect(html).toMatch(/<article[^>]*class="prose-print"[^>]*data-title="Test Article"/);
    });

    it("renders cover page only when postImage is set", () => {
        const without = buildPrintDocument(baseArticle, "<p>x</p>");
        expect(without).not.toMatch(/class="cover"/);

        const withImg = buildPrintDocument(
            { ...baseArticle, postImage: "https://x/cover.jpg" },
            "<p>x</p>",
        );
        expect(withImg).toMatch(/class="cover"/);
        expect(withImg).toMatch(/src="https:\/\/x\/cover\.jpg"/);
    });

    it("renders TOC only when tableOfContents is non-empty", () => {
        const without = buildPrintDocument(baseArticle, "<p>x</p>");
        expect(without).not.toMatch(/class="toc"/);

        const withToc = buildPrintDocument(
            {
                ...baseArticle,
                tableOfContents: [
                    { id: "intro", title: "Intro" },
                    { id: "more", title: "More" },
                ],
            },
            "<p>x</p>",
        );
        expect(withToc).toMatch(/class="toc"/);
        expect(withToc).toMatch(/href="#intro"/);
        expect(withToc).toMatch(/href="#more"/);
    });

    it("HTML-escapes dangerous title characters", () => {
        const html = buildPrintDocument(
            { ...baseArticle, title: 'A "quoted" <script>title' },
            "<p>x</p>",
        );
        // Quotes inside the data-title attribute must be escaped
        expect(html).not.toMatch(/data-title="A "quoted"/);
        expect(html).toMatch(/data-title="A &quot;quoted&quot; &lt;script&gt;title"/);
    });
});
