import { command } from "$app/server";
import * as v from "valibot";
import { renderArticle } from "$lib/server/articleRenderer";
import { buildPrintDocument } from "$lib/server/printDocument";
import { PDF_SERVICE_URL, PDF_SERVICE_SECRET } from "$env/static/private";

function slugify(title: string, fallback = "article"): string {
	const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
	return slug || fallback;
}

export const generatePdf = command(v.string(), async (slug) => {
	const { html, article } = await renderArticle(slug, { mode: "print" });
	if (!article) {
		throw new Error("Article not found");
	}

	const printHtml = buildPrintDocument(article, html);
	const filename = `${slugify(article.title)}.pdf`;

	const res = await fetch(`${PDF_SERVICE_URL}/internal/pdf`, {
		method: "POST",
		headers: {
			"content-type": "application/json",
			"x-internal-secret": PDF_SERVICE_SECRET,
		},
		body: JSON.stringify({ html: printHtml, filename }),
	});
	if (!res.ok) {
		throw new Error(`PDF service returned ${res.status}`);
	}

	return {
		bytes: new Uint8Array(await res.arrayBuffer()),
		filename,
	};
});
