import { fetchIframeHtml } from "@/services/iframe";

/**
 * Sync iframe srcdoc with the page theme.
 *
 * Each iframe rendered by the backend is tagged with `data-iframe-id`
 * (the Medium media id) and `data-iframe-theme` (the theme that was
 * baked into its current srcdoc). When the page theme differs from
 * the iframe's baked theme, we refetch a themed variant of the HTML
 * via /api/iframe/{id}?theme=... and swap srcdoc in place.
 *
 * Costs (see /tmp/iframe-theme-test-D.html for a hands-on demo):
 *   - in-iframe state resets on every swap
 *   - in-iframe scroll position resets
 *   - brief opacity flash mid-swap
 *
 * Returns a disposer the caller can use to stop syncing.
 */
export function startIframeThemeSync(
	getTheme: () => "light" | "dark",
	rootSelector: string = ".prose",
): () => void {
	const root = document.querySelector(rootSelector);
	if (!root) return () => {};

	const inflight = new Map<HTMLIFrameElement, AbortController>();

	function findIframes(): HTMLIFrameElement[] {
		return Array.from(
			root!.querySelectorAll<HTMLIFrameElement>("iframe[data-iframe-id]"),
		);
	}

	async function swap(iframe: HTMLIFrameElement, theme: "light" | "dark") {
		const id = iframe.dataset.iframeId;
		if (!id) return;
		// Already in sync — nothing to do
		if (iframe.dataset.iframeTheme === theme) return;

		// Cancel any prior in-flight swap on this iframe
		inflight.get(iframe)?.abort();
		const ctrl = new AbortController();
		inflight.set(iframe, ctrl);

		try {
			iframe.style.transition ||= "opacity 180ms ease";
			iframe.style.opacity = "0";

			const html = await fetchIframeHtml(id, theme);
			if (ctrl.signal.aborted) return;

			iframe.srcdoc = html;
			iframe.dataset.iframeTheme = theme;

			// Restore opacity once the iframe document has parsed
			const onLoad = () => {
				iframe.style.opacity = "1";
				iframe.removeEventListener("load", onLoad);
			};
			iframe.addEventListener("load", onLoad);
		} catch (err) {
			if (!ctrl.signal.aborted) {
				console.warn(`Iframe theme swap failed for ${id}:`, err);
				iframe.style.opacity = "1";
			}
		} finally {
			if (inflight.get(iframe) === ctrl) inflight.delete(iframe);
		}
	}

	function syncAll() {
		const theme = getTheme();
		for (const iframe of findIframes()) void swap(iframe, theme);
	}

	// Initial sync (catches dark-mode users on first load)
	syncAll();

	return () => {
		for (const ctrl of inflight.values()) ctrl.abort();
		inflight.clear();
	};
}
