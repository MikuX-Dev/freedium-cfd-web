import apiFetch from "@/api";
import type { Article } from "$lib/types";

interface RenderRequest {
	content: string;
	frontmatter?: boolean;
}

interface RenderResponse {
	markdown: string;
	service: string;
}

export async function render(content: string, frontmatter = false): Promise<RenderResponse> {
	let response: RenderResponse | undefined;
	try {
		response = await apiFetch<RenderResponse>("/render", {
			method: "POST",
			body: JSON.stringify({
				content,
				frontmatter,
			}),
			headers: {
				"Content-Type": "application/json",
			},
		});
	} catch (err: unknown) {
		// ofetch throws on non-2xx HTTP responses with a status on the error.
		// Re-throw with an UPSTREAM_<status>-prefixed message so the SSR
		// loader's catch-all in +page.server.ts maps it to the
		// `upstream_error` outcome on freedium_web_article_fetch_total.
		// Errors without an HTTP status (DNS, connection refused, timeout)
		// propagate unchanged so the same catch-all labels them `network_fail`.
		const status =
			(err as { status?: number; response?: { status?: number } })?.status ??
			(err as { response?: { status?: number } })?.response?.status;
		if (typeof status === "number") {
			throw new Error(`UPSTREAM_${status}`);
		}
		throw err;
	}

	if (!response) {
		throw new Error("Failed to render content");
	}

	return response;
}
