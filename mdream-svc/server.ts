/**
 * mdream-svc — tiny HTTP sidecar that converts HTML → Markdown via mdream.
 *
 * The Python backend can't run mdream (Node/NAPI lib) in-process, so it POSTs
 * raw HTML here and gets clean, LLM-optimized markdown back. Isolated container
 * with hard resource limits (mdream is fast + zero-dep, but the box is small).
 *
 *   POST /  body: text/html        → 200 text/markdown
 *   GET  /healthz                  → 200 ok
 *
 * Used by NytService: NYT's hybridBody.main.contents (full article HTML) →
 * markdown. `minimal` preset + main-content extraction strips nav/boilerplate.
 */
import { htmlToMarkdown } from "mdream";

const PORT = Number(Bun.env.PORT ?? 8085);
const MAX_BYTES = 4 * 1024 * 1024; // article HTML is ~500KB; cap defensively

Bun.serve({
	port: PORT,
	idleTimeout: 30,
	async fetch(req) {
		const url = new URL(req.url);
		if (req.method === "GET" && (url.pathname === "/healthz" || url.pathname === "/")) {
			return new Response("ok", { headers: { "content-type": "text/plain" } });
		}
		if (req.method !== "POST") {
			return new Response("method not allowed", { status: 405 });
		}
		const html = await req.text();
		if (!html) return new Response("empty body", { status: 400 });
		if (html.length > MAX_BYTES) return new Response("too large", { status: 413 });
		try {
			// minimal preset = no front-matter/extras; isolate the article body so
			// NYT page chrome (scripts, nav, paywall wrappers) is dropped.
			const md = htmlToMarkdown(html, { preset: "minimal" });
			return new Response(md, { headers: { "content-type": "text/markdown; charset=utf-8" } });
		} catch (e) {
			return new Response(`mdream error: ${(e as Error).message}`, { status: 500 });
		}
	},
});

console.log(`mdream-svc listening on :${PORT}`);
