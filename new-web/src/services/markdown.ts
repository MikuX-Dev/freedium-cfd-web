import config from "@/config";

/** URL of the backend's article download endpoint. The browser handles the
 * download natively via Content-Disposition; the frontend just needs to
 * navigate to this URL (e.g. via `<a>.click()`). The gist resolution
 * strategy is hardcoded server-side. */
export function articleDownloadUrl(slug: string): string {
	const params = new URLSearchParams({ url: slug });
	return `${config.API_URL}/articles/download?${params}`;
}
