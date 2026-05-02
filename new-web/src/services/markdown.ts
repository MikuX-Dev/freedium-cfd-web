import apiFetch from "@/api";

interface ResolveGistsResponse {
	markdown: string;
}

/** Strategy for resolving gist iframes:
 *  - `raw`: one GET to /raw per gist, bare ``` fences, no filename/language,
 *    first file only — fast and minimal.
 *  - `rich`: gist HTML page + per-file raw URLs, **filename** headers and
 *    ```lang fences, full multi-file support — more requests, more bytes. */
export type ResolveGistsMode = "raw" | "rich";

/** Ask the backend to replace gist iframes inside the rendered markdown
 * with markdown code fences. Used for the article download flow so the
 * saved .md contains real source code instead of raw iframe HTML. */
export async function resolveGists(
	markdown: string,
	mode: ResolveGistsMode = "raw",
): Promise<string> {
	const response = await apiFetch<ResolveGistsResponse>(
		"/markdown/resolve-gists",
		{
			method: "POST",
			body: JSON.stringify({ markdown, mode }),
			headers: { "Content-Type": "application/json" },
		},
	);
	if (!response) throw new Error("Failed to resolve gists");
	return response.markdown;
}
