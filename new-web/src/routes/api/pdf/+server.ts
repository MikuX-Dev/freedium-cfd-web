import { error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { renderArticle } from "$lib/server/articleRenderer";
import { buildPrintDocument } from "$lib/server/printDocument";
import { env } from "$env/dynamic/private";

function slugify(title: string, fallback = "article"): string {
	const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
	return slug || fallback;
}

export const POST: RequestHandler = async ({ request }) => {
	const { slug } = await request.json();
	if (!slug) {
		throw error(400, "Missing slug");
	}

	// SvelteKit's [...slug] route collapses // to / in path segments.
	// Restore the protocol double-slash so the backend can match the URL.
	const normalizedSlug = slug.replace(/^(https?):\/([^/])/, "$1://$2");

	const { html, article } = await renderArticle(normalizedSlug, { mode: "print" });
	if (!article) {
		throw error(404, "Article not found");
	}

	const printHtml = buildPrintDocument(article, html);
	const filename = `${slugify(article.title)}.pdf`;

	const pdfRes = await fetch(`${env.PDF_SERVICE_URL}/internal/pdf`, {
		method: "POST",
		headers: {
			"content-type": "application/json",
			"x-internal-secret": env.PDF_SERVICE_SECRET || "",
		},
		body: JSON.stringify({ html: printHtml, filename, url: normalizedSlug }),
	});

	if (!pdfRes.ok) {
		throw error(502, `PDF service returned ${pdfRes.status}`);
	}

	const pdfBytes = await pdfRes.arrayBuffer();

	return new Response(pdfBytes, {
		status: 200,
		headers: {
			"content-type": "application/pdf",
			"content-disposition": `attachment; filename="${filename}"`,
		},
	});
};
