/**
 * Sync iframe contents with the page theme.
 *
 * Each iframe rendered by the backend is tagged with `data-iframe-id` and
 * served via `srcdoc`, which makes it same-origin to the parent page. We
 * inject (or remove) a `<style>` element directly into `iframe.contentDocument`
 * to override the upstream embed's colors when the page is in dark mode.
 *
 * No network round-trip on toggle, no srcdoc swap, no in-iframe state loss,
 * no scroll reset, no flash. Idempotent — safe to call repeatedly.
 *
 * Returns a disposer that removes any pending load listeners.
 */

const STYLE_ID = "freedium-theme-overrides";

const IFRAME_DARK_STYLES = `
body { background:#0c0c0c !important; color:#d4d4d4 !important; }
a, .gist a { color:#58a6ff !important; }
.gist,
.gist .gist-data,
.gist .gist-file,
.gist .gist-meta,
.gist .blob-wrapper,
.gist .blob-code-inner,
.gist .markdown-body,
.gist .markdown-body pre,
.gist .markdown-body code { background:#0c0c0c !important; color:#d4d4d4 !important; border-color:#2a2a2a !important; }
.gist .blob-num { background:#161616 !important; color:#6a6a6a !important; border-color:#2a2a2a !important; }
.gist .gist-meta,
.gist .gist-meta strong { color:#888 !important; }
.gist .pl-c  { color:#7a7a7a !important; }
.gist .pl-s,
.gist .pl-s1,
.gist .pl-pds { color:#a5d6a7 !important; }
.gist .pl-k,
.gist .pl-kos { color:#ff7b72 !important; }
.gist .pl-e,
.gist .pl-en { color:#d2a8ff !important; }
.gist .pl-c1,
.gist .pl-cn { color:#79c0ff !important; }
.gist .pl-v   { color:#ffa657 !important; }
`.trim();

// Set on the host <iframe> element once we've had a chance to inject (or
// confirm absent) the dark-theme overrides. Paired with a CSS rule in
// ArticlePage.css that hides un-themed iframes when dark mode is active —
// without this, the iframe paints its own light styles before our override
// lands and the user sees a FOUC flash on first load.
const THEMED_ATTR = "data-iframe-themed";

function applyTheme(iframe: HTMLIFrameElement, theme: "light" | "dark"): boolean {
	let doc: Document | null;
	try {
		doc = iframe.contentDocument;
	} catch {
		// Defensive: cross-origin would throw, but srcdoc iframes are same-origin.
		return false;
	}
	if (!doc?.documentElement) return false;
	const head = doc.head ?? doc.documentElement;
	const existing = doc.getElementById(STYLE_ID);
	if (theme === "dark") {
		if (!existing) {
			const style = doc.createElement("style");
			style.id = STYLE_ID;
			style.textContent = IFRAME_DARK_STYLES;
			head.appendChild(style);
		}
	} else if (existing) {
		existing.remove();
	}
	iframe.setAttribute(THEMED_ATTR, "");
	return true;
}

export function startIframeThemeSync(
	getTheme: () => "light" | "dark",
	rootSelector: string = ".prose",
): () => void {
	const root = document.querySelector(rootSelector);
	if (!root) return () => {};

	const listeners = new Map<HTMLIFrameElement, () => void>();

	function ensure(iframe: HTMLIFrameElement) {
		// Try immediately — works if the iframe document is already parsed.
		if (applyTheme(iframe, getTheme())) return;
		// Otherwise wait for the iframe's load event before applying.
		const onLoad = () => {
			applyTheme(iframe, getTheme());
			// Failsafe: even if applyTheme couldn't reach contentDocument
			// (e.g. cross-origin in some unforeseen case), reveal the iframe
			// rather than leaving it hidden by the CSS gate forever.
			iframe.setAttribute(THEMED_ATTR, "");
		};
		iframe.addEventListener("load", onLoad);
		listeners.set(iframe, () => iframe.removeEventListener("load", onLoad));
	}

	const iframes = root.querySelectorAll<HTMLIFrameElement>(
		"iframe[data-iframe-id]",
	);
	for (const iframe of iframes) ensure(iframe);

	return () => {
		for (const off of listeners.values()) off();
		listeners.clear();
	};
}
