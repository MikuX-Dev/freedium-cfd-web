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

	const loadListeners = new Map<HTMLIFrameElement, () => void>();

	/** Apply or remove dark theme on a single iframe. If the iframe document
	 * isn't ready yet, waits for the load event (or readyState). Safe to call
	 * on already-themed iframes (idempotent). */
	function ensure(iframe: HTMLIFrameElement) {
		const doc = iframe.contentDocument;
		// Try immediate — works when the iframe document is already parsed.
		if (doc?.documentElement) {
			applyTheme(iframe, getTheme());
			return;
		}
		// Not ready. If already loaded (readyState complete) but documentElement
		// is null, something went wrong — reveal anyway so it's not stuck hidden.
		if (doc?.readyState === "complete") {
			iframe.setAttribute(THEMED_ATTR, "");
			return;
		}
		// Still loading — register load listener.
		const onLoad = () => {
			applyTheme(iframe, getTheme());
			loadListeners.delete(iframe);
		};
		iframe.addEventListener("load", onLoad, { once: true });
		loadListeners.set(iframe, () => iframe.removeEventListener("load", onLoad));
	}

	// Re-theme ALL existing iframes (called on initial run AND on theme toggle
	// from the caller's $effect cleanup/rerun cycle, via observer).
	function themeAll() {
		for (const iframe of root!.querySelectorAll<HTMLIFrameElement>("iframe[data-iframe-id]")) {
			ensure(iframe);
		}
	}
	themeAll();

	// MutationObserver catches iframes added AFTER the initial scan — e.g.
	// when { @html content } renders them into the prose container AFTER the
	// $effect fired (a common Svelte streaming/dynamic-content race).
	const observer = new MutationObserver((mutations) => {
		for (const m of mutations) {
			for (const node of m.addedNodes) {
				if (node instanceof HTMLIFrameElement && node.hasAttribute("data-iframe-id")) {
					ensure(node);
				} else if (node instanceof Element) {
					for (const iframe of node.querySelectorAll<HTMLIFrameElement>("iframe[data-iframe-id]")) {
						ensure(iframe);
					}
				}
			}
		}
	});
	observer.observe(root, { childList: true, subtree: true });

	return () => {
		observer.disconnect();
		for (const off of loadListeners.values()) off();
		loadListeners.clear();
	};
}
