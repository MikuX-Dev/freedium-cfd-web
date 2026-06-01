import { ofetch } from "ofetch";
import config from "./config";

let _getClientUa: (() => string) | null = null;

// Backend renders can take 30-90s on a cold cache for big articles
// (long Medium pages with many images go through the WARP proxy chain,
// each Medium GraphQL hop adds 200-500ms). Node's undici defaults bite
// at 30s — bump the SSR-side fetch timeout to 120s so the user gets
// the rendered article instead of a 500 + cached "Failed to render".
const apiFetch = ofetch.create({
	baseURL: config.API_URL,
	timeout: 120_000,
	// Forward the real browser/bot User-Agent (stashed by hooks.server.ts
	// in an AsyncLocalStorage) as X-Client-UA — the backend logs it in
	// rendered-links / errored-links so we can trace which UA visited
	// which article. import.meta.env.SSR guards the server-only import
	// from the client bundle (Vite tree-shakes it away).
	async onRequest({ options }) {
		if (import.meta.env.SSR && _getClientUa === null) {
			const m = await import("$lib/server/client-ua");
			_getClientUa = m.getClientUa;
		}
		const ua = _getClientUa?.() ?? "";
		if (ua) {
			options.headers = {
				...((options.headers as Record<string, string> | undefined) ?? {}),
				"X-Client-UA": ua,
			};
		}
	},
});

export default apiFetch;
