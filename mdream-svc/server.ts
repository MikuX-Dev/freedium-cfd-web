/**
 * mdream-svc — HTTP sidecar: HTML → clean article Markdown via mdream.
 *
 * The Python backend can't run mdream (Node/NAPI) in-process, so NytService
 * POSTs NYT's hybridBody.main.contents (a ~500KB full HTML document) here and
 * gets article markdown back. Isolated container, hard resource limits.
 *
 *   POST /  body: text/html        → 200 text/markdown
 *   GET  /healthz                  → 200 ok
 *
 * mdream's own main-content heuristic doesn't recognise NYT's hybrid layout
 * (it returns just <head> meta), so we first isolate the article body with a
 * DOM parser (section[name="articleBody"] → <article> → <main> → <body>),
 * then convert only that. Inline links/emphasis are preserved.
 */
import { parse } from "node-html-parser";
import { htmlToMarkdown } from "mdream";

const PORT = Number(Bun.env.PORT ?? 8085);
const MAX_BYTES = 4 * 1024 * 1024; // article HTML ~500KB; cap defensively

// Priority order of selectors for the readable article body.
const BODY_SELECTORS = [
	'section[name="articleBody"]',
	"article",
	"main",
	"body",
];

function extractArticleMarkdown(html: string): string {
	const root = parse(html);
	for (const sel of BODY_SELECTORS) {
		const el = root.querySelector(sel);
		if (el && el.outerHTML.length > 200) {
			const md = htmlToMarkdown(el.outerHTML).trim();
			if (md.length > 50) return md;
		}
	}
	// Last resort: convert the whole document.
	return htmlToMarkdown(html).trim();
}

Bun.serve({
	port: PORT,
	idleTimeout: 30,
	async fetch(req) {
		const url = new URL(req.url);
		if (req.method === "GET" && (url.pathname === "/healthz" || url.pathname === "/")) {
			return new Response("ok", { headers: { "content-type": "text/plain" } });
		}
		if (req.method !== "POST") return new Response("method not allowed", { status: 405 });

		const html = await req.text();
		if (!html) return new Response("empty body", { status: 400 });
		if (html.length > MAX_BYTES) return new Response("too large", { status: 413 });
		try {
			const md = extractArticleMarkdown(html);
			return new Response(md, {
				headers: { "content-type": "text/markdown; charset=utf-8" },
			});
		} catch (e) {
			return new Response(`mdream error: ${(e as Error).message}`, { status: 500 });
		}
	},
});

console.log(`mdream-svc listening on :${PORT}`);
