import { renderArticle } from "$lib/server/articleRenderer";
import { recordArticleFetch } from "$lib/server/metrics";
import type { PageServerLoad } from "./$types";
import type { ArticleErrorCode } from "$lib/types";

const ErrorCodes: Record<ArticleErrorCode, ArticleErrorCode> = {
	ARTICLE_NOT_FOUND: "ARTICLE_NOT_FOUND",
	RENDER_ERROR: "RENDER_ERROR",
	COMPILE_ERROR: "COMPILE_ERROR",
	INTERNAL_ERROR: "INTERNAL_ERROR",
};

export const load: PageServerLoad = async ({ params, setHeaders }) => {
	try {
		const start = performance.now();
		const { html, markdown, article, cacheStatus } = await renderArticle(params.slug);
		const renderTimeMs = Math.round(performance.now() - start);

		setHeaders({
			"X-Cache-Status": cacheStatus,
			"X-Render-Time": `${renderTimeMs}ms`,
		});

		recordArticleFetch("success");
		return {
			slug: params.slug,
			loading: false,
			content: html,
			markdown,
			article,
			error: null,
		};
	} catch (err) {
		const message = (err as Error)?.message ?? "";
		if (message === "ARTICLE_NOT_FOUND") {
			recordArticleFetch("not_found");
			return {
				slug: params.slug,
				loading: false,
				content: null,
				markdown: null,
				article: null,
				error: {
					status: 404,
					message: "Article not found",
					code: ErrorCodes.ARTICLE_NOT_FOUND,
				},
			};
		}
		console.error("Failed to render article:", err);
		recordArticleFetch(
			message.startsWith("UPSTREAM_") ? "upstream_error" : "network_fail",
		);
		return {
			slug: params.slug,
			loading: false,
			content: null,
			markdown: null,
			article: null,
			error: {
				status: 500,
				message: "Failed to render article",
				code: ErrorCodes.RENDER_ERROR,
				details: import.meta.env.DEV ? (err as Error).message : undefined,
			},
		};
	}
};
