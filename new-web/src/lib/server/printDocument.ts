import printStyles from "./printStyles.css?raw";
import type { ArticleMetadata } from "./articleRenderer";
import config from "@/config";

/** Freedium URL for a Medium link, so PDF links open the Freedium version. */
function freediumUrl(mediumUrl: string): string {
	return `${config.SITE_URL}/${mediumUrl}`;
}

/** Rewrite in-article links that point at Medium so they open through
 * Freedium instead — keeps PDF readers on Freedium. Matches medium.com and
 * its subdomains (e.g. *.medium.com), leaves all other links untouched. */
function rewriteMediumLinks(html: string): string {
	return html.replace(
		/href="(https?:\/\/(?:[a-z0-9-]+\.)*medium\.com\/[^"]+)"/gi,
		(_m, link) => `href="${config.SITE_URL}/${link}"`,
	);
}

function escapeHtml(s: string): string {
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function fmtDate(iso: string | null): string {
    if (!iso) return "";
    const d = new Date(iso);
    return isNaN(d.getTime())
        ? ""
        : d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

function renderCover(article: ArticleMetadata): string {
    if (!article.postImage) return "";
    const publishedStr = fmtDate(article.publishedAt ?? article.date);
    const updatedStr = article.updatedAt ? fmtDate(article.updatedAt) : "";
    const showUpdated = updatedStr !== "" && updatedStr !== publishedStr;
    return `
    <section class="cover">
        <div class="cover-content">
            <div class="cover-image" style="background-image:url('${escapeHtml(article.postImage)}')"></div>
            <h1 class="cover-title">${escapeHtml(article.title)}</h1>
            ${article.subtitle ? `<p class="cover-subtitle">${escapeHtml(article.subtitle)}</p>` : ""}
            <div class="cover-meta">
                <p><strong>${escapeHtml((article.authors ?? []).map((a) => a.name).join(" and "))}</strong></p>
                ${publishedStr ? `<p>Published ${escapeHtml(publishedStr)}</p>` : ""}
                ${showUpdated ? `<p>Updated ${escapeHtml(updatedStr)}</p>` : ""}
                ${article.isFree !== null ? `<p>Free: ${article.isFree ? "Yes" : "No"}</p>` : ""}
                ${article.url ? `<p><a href="${escapeHtml(freediumUrl(article.url))}">Read on Freedium</a> · <a href="${escapeHtml(article.url)}">original</a></p>` : ""}
            </div>
        </div>
    </section>`;
}

function renderToc(article: ArticleMetadata): string {
    if (article.tableOfContents.length === 0) return "";
    const items = article.tableOfContents
        .map(
            (t) =>
                `<li><a href="#${escapeHtml(t.id)}"><span>${escapeHtml(t.title)}</span></a></li>`,
        )
        .join("");
    return `
    <nav class="toc">
        <h2>Contents</h2>
        <ol>${items}</ol>
    </nav>`;
}

export function buildPrintDocument(article: ArticleMetadata, contentHtml: string): string {
    return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>${escapeHtml(article.title)}</title>
<style>${printStyles}</style>
</head>
<body>
${renderCover(article)}
${renderToc(article)}
<article class="prose-print" data-title="${escapeHtml(article.title)}">
${rewriteMediumLinks(contentHtml)}
</article>
</body>
</html>`;
}
