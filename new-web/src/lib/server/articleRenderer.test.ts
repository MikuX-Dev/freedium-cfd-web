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
