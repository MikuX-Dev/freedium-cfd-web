import config from "@/config";

/** Fetch iframe HTML for `iframeId` with `theme`-specific CSS baked in.
 * Used to swap iframe srcdoc when the page theme toggles, without
 * re-rendering the entire article. Goes through the browser's fetch
 * directly (rather than the JSON-typed apiFetch wrapper) because the
 * endpoint returns text/html. */
export async function fetchIframeHtml(
	iframeId: string,
	theme: "light" | "dark",
): Promise<string> {
	const url = `${config.API_URL}/iframe/${encodeURIComponent(iframeId)}?theme=${theme}`;
	const response = await fetch(url, {
		method: "GET",
		headers: { Accept: "text/html" },
	});
	if (!response.ok) {
		throw new Error(`Iframe fetch failed (${response.status}): ${iframeId}`);
	}
	return await response.text();
}
