import config from "@/config";

/** Strategy for resolving gist iframes:
 *  - `raw`: one GET to /raw per gist, bare ``` fences, no filename/language,
 *    first file only — fast and minimal.
 *  - `rich`: gist HTML page + per-file raw URLs, **filename** headers and
 *    ```lang fences, full multi-file support — more requests, more bytes. */
export type ResolveGistsMode = "raw" | "rich";

/** URL of the backend's article download endpoint. The browser handles the
 * download natively via Content-Disposition; the frontend just needs to
 * navigate to this URL (e.g. via `<a>.click()`). */
export function articleDownloadUrl(
	slug: string,
	mode: ResolveGistsMode = "raw",
): string {
	const params = new URLSearchParams({ url: slug, mode });
	return `${config.API_URL}/articles/download?${params}`;
}
