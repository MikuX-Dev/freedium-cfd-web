/** URL for downloading an article as markdown. Points at the SvelteKit
 * server route which proxies the request to the backend internally. */
export function articleDownloadUrl(slug: string): string {
	const params = new URLSearchParams({ url: slug });
	return `/api/download?${params}`;
}
