import apiFetch from "@/api";

interface ResolveGistsResponse {
	markdown: string;
}

/** Ask the backend to replace gist iframes inside the rendered markdown
 * with markdown code fences. Used for the article download flow so the
 * saved .md contains real source code instead of raw iframe HTML. */
export async function resolveGists(markdown: string): Promise<string> {
	const response = await apiFetch<ResolveGistsResponse>(
		"/markdown/resolve-gists",
		{
			method: "POST",
			body: JSON.stringify({ markdown }),
			headers: { "Content-Type": "application/json" },
		},
	);
	if (!response) throw new Error("Failed to resolve gists");
	return response.markdown;
}
