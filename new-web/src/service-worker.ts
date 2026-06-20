/// <reference types="@sveltejs/kit" />
/**
 * Freedium PWA service worker (native SvelteKit — no Workbox/plugin deps).
 *
 * Strategy:
 *  - Versioned build assets + static files: precached on install, cache-first
 *    (they're content-hashed / immutable, so cache hits are always correct).
 *  - Page navigations (home + articles): network-first with a cache fallback,
 *    so you read fresh content online and previously-opened pages offline.
 *    Final fallback = an inline branded offline page (no /offline route, so no
 *    prerender/layout coupling).
 *  - Image proxy /img/*: cache-first runtime cache (capped) so a visited
 *    article's images render offline. Opaque (cross-origin CDN) responses are
 *    cached best-effort.
 *  - Everything else (API/data): passthrough — never cached.
 *
 * SvelteKit auto-registers this file in production builds.
 */
import { build, files, prerendered, version } from "$service-worker";

const sw = self as unknown as ServiceWorkerGlobalScope;

const PRECACHE = `precache-${version}`;
const NAV_CACHE = `nav-${version}`;
const IMG_CACHE = `img-${version}`;
const KEEP = new Set([PRECACHE, NAV_CACHE, IMG_CACHE]);

// Content-hashed assets + static files + any prerendered pages.
const PRECACHE_URLS = [...build, ...files, ...prerendered];
const PRECACHE_SET = new Set(PRECACHE_URLS);

const NAV_MAX = 60; // cap cached article/page responses
const IMG_MAX = 150; // cap cached proxied images

const OFFLINE_HTML = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Offline · Freedium</title>
<style>html{color-scheme:light dark}body{margin:0;min-height:100vh;display:flex;
align-items:center;justify-content:center;font-family:system-ui,sans-serif;
background:#fff;color:#111}@media(prefers-color-scheme:dark){body{background:#0c0c0c;color:#d4d4d4}}
.c{max-width:30rem;padding:2rem;text-align:center}h1{font-size:1.5rem;margin:0 0 .5rem}
p{opacity:.7;line-height:1.5}</style></head>
<body><div class="c"><h1>You're offline</h1>
<p>Reconnect to read new articles. Pages you've already opened are still available offline.</p>
</div></body></html>`;

sw.addEventListener("install", (event) => {
	event.waitUntil(
		caches
			.open(PRECACHE)
			.then((cache) => cache.addAll(PRECACHE_URLS))
			.then(() => sw.skipWaiting()),
	);
});

sw.addEventListener("activate", (event) => {
	event.waitUntil(
		(async () => {
			for (const key of await caches.keys()) {
				if (!KEEP.has(key)) await caches.delete(key);
			}
			await sw.clients.claim();
		})(),
	);
});

/** Trim a cache to its newest `max` entries (FIFO by insertion order). */
async function trim(cacheName: string, max: number): Promise<void> {
	const cache = await caches.open(cacheName);
	const keys = await cache.keys();
	if (keys.length <= max) return;
	for (const req of keys.slice(0, keys.length - max)) {
		await cache.delete(req);
	}
}

async function cacheFirstStatic(request: Request): Promise<Response> {
	const cached = await caches.match(request);
	return cached ?? fetch(request);
}

async function imageStrategy(request: Request): Promise<Response> {
	const cache = await caches.open(IMG_CACHE);
	const cached = await cache.match(request);
	if (cached) return cached;
	try {
		const res = await fetch(request);
		// Cache same-origin OK or cross-origin opaque CDN responses; never the
		// 307 redirect itself (not cacheable). Best-effort.
		if (res && (res.ok || res.type === "opaque")) {
			await cache.put(request, res.clone());
			await trim(IMG_CACHE, IMG_MAX);
		}
		return res;
	} catch {
		return cached ?? Response.error();
	}
}

async function navigationStrategy(request: Request): Promise<Response> {
	const cache = await caches.open(NAV_CACHE);
	try {
		const res = await fetch(request);
		if (res && res.ok && res.type === "basic") {
			await cache.put(request, res.clone());
			await trim(NAV_CACHE, NAV_MAX);
		}
		return res;
	} catch {
		const cached = await cache.match(request);
		if (cached) return cached;
		return new Response(OFFLINE_HTML, {
			status: 503,
			headers: { "content-type": "text/html; charset=utf-8" },
		});
	}
}

sw.addEventListener("fetch", (event) => {
	const { request } = event;
	if (request.method !== "GET") return;

	const url = new URL(request.url);
	if (url.protocol !== "http:" && url.protocol !== "https:") return;

	const sameOrigin = url.origin === location.origin;

	if (sameOrigin && PRECACHE_SET.has(url.pathname)) {
		event.respondWith(cacheFirstStatic(request));
		return;
	}
	if (sameOrigin && url.pathname.startsWith("/img/")) {
		event.respondWith(imageStrategy(request));
		return;
	}
	if (request.mode === "navigate") {
		event.respondWith(navigationStrategy(request));
		return;
	}
	// Everything else: default network passthrough (API, data, cross-origin).
});
