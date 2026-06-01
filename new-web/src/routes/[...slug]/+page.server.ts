import { renderArticle } from "$lib/server/articleRenderer";
import { recordArticleFetch } from "$lib/server/metrics";
import type { PageServerLoad } from "./$types";

/**
 * Return the render result as a promise so SvelteKit streams the page:
 * the loading skeleton arrives in the first HTML chunk, the rendered
 * article body arrives later when the backend finishes. This means the
 * user sees the page instantly (<100 ms TTFB) even on a cold cache
 * where the backend takes 30–90 s to render a large article.
 */
export const load: PageServerLoad = async ({ params, request }) => {
	const start = performance.now();
	const clientUa = request.headers.get("User-Agent") ?? "";

	// Fire-and-forget: SvelteKit unwraps this promise and streams
	// the resolved data. The page component uses {#await} to show
	// a skeleton while this is pending.
	const streamed = renderArticle(params.slug, { clientUa }).then((result) => {
		const renderTimeMs = Math.round(performance.now() - start);
		recordArticleFetch("success");
		return {
			html: result.html,
			markdown: result.markdown,
			article: result.article,
			cacheStatus: result.cacheStatus,
			renderTimeMs,
			error: null as { status: number; message: string; code?: string; details?: string } | null,
		};
	}).catch((err: unknown) => {
		const message = (err as Error)?.message ?? "";
		if (message === "ARTICLE_NOT_FOUND") {
			recordArticleFetch("not_found");
			return {
				html: null as string | null,
				markdown: null as string | null,
				article: null as import("$lib/types").ArticlePageData["article"] | null,
				cacheStatus: "miss" as string,
				renderTimeMs: Math.round(performance.now() - start),
				error: {
					status: 404,
					message: "Article not found",
					code: "ARTICLE_NOT_FOUND",
				},
			};
		}
		console.error("Failed to render article:", err);
		recordArticleFetch(
			message.startsWith("UPSTREAM_") ? "upstream_error" : "network_fail",
		);
		return {
			html: null,
			markdown: null,
			article: null,
			cacheStatus: "miss",
			renderTimeMs: Math.round(performance.now() - start),
			error: {
				status: 500,
				message: "Failed to render article",
				code: "RENDER_ERROR",
				details: import.meta.env.DEV ? (err as Error).message : undefined,
			},
		};
	});

	return {
		slug: params.slug,
		streamed,
	};
};
