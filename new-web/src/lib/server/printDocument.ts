import printStyles from "./printStyles.css?raw";
import type { ArticleMetadata } from "./articleRenderer";

function escapeHtml(s: string): string {
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function renderCover(article: ArticleMetadata): string {
    if (!article.postImage) return "";
    const date = new Date(article.date);
    const dateStr = isNaN(date.getTime())
        ? ""
        : date.toLocaleDateString("en-US", {
              year: "numeric",
              month: "long",
              day: "numeric",
          });
    return `
    <section class="cover">
        <img class="cover-image" src="${escapeHtml(article.postImage)}" alt=""/>
        <div class="cover-content">
            <h1 class="cover-title">${escapeHtml(article.title)}</h1>
            ${article.subtitle ? `<p class="cover-subtitle">${escapeHtml(article.subtitle)}</p>` : ""}
            <div class="cover-meta">
                <p><strong>${escapeHtml(article.author.name)}</strong></p>
                ${dateStr ? `<p>${escapeHtml(dateStr)}</p>` : ""}
                ${article.url ? `<p><a href="${escapeHtml(article.url)}">${escapeHtml(article.url)}</a></p>` : ""}
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
${contentHtml}
</article>
</body>
</html>`;
}
