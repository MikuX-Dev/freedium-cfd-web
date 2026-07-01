/**
 * RSS endpoints.
 *
 *   GET /rss                → feed of recently-unlocked articles (from the
 *                             backend recent-posts buffer).
 *   GET /rss?url=<feed>     → PROXY: fetch a Medium/NYT source feed, rewrite
 *                             each item link to its Freedium URL, and inline the
 *                             full paywall-free article into <content:encoded>
 *                             so it reads inline in any RSS reader.
 *
 * Lives in the web tier because full-content inline needs the markdown→HTML
 * pipeline (renderArticle), which also uses the L2 render cache — so repeat
 * polls are cheap.
 */
import { error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import config from "@/config";
import { renderArticle } from "$lib/server/articleRenderer";
import Parser from "rss-parser";

// Feed source hosts + renderable article hosts we allow (SSRF guard: no
// arbitrary fetches, no private-network hosts).
const HOST_ALLOW = /(^|\.)(medium\.com|nytimes\.com)$/i;

const MAX_ITEMS = 12; // cap per proxied feed (bounds render load)
const RENDER_CONCURRENCY = 4;
const PER_ITEM_TIMEOUT_MS = 10_000;

function escapeXml(s: string): string {
	return (s || "")
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&apos;");
}

// CDATA-safe: split any accidental "]]>" so it can't close the section early.
function cdata(html: string): string {
	return `<![CDATA[${(html || "").replace(/]]>/g, "]]]]><![CDATA[>")}]]>`;
}

// Relative-root URLs (/img/…, /… ) → absolute so RSS readers can load them.
function absolutize(html: string): string {
	return html
		.replace(/(\ssrc=")\/(?!\/)/g, `$1${config.SITE_URL}/`)
		.replace(/(\shref=")\/(?!\/)/g, `$1${config.SITE_URL}/`);
}

interface FeedItem {
	title: string;
	link: string;
	guid: string;
	pubDate?: string;
	creator?: string;
	description?: string;
	contentHtml?: string;
}

function renderItem(i: FeedItem): string {
	return [
		"<item>",
		`<title>${escapeXml(i.title)}</title>`,
		`<link>${escapeXml(i.link)}</link>`,
		`<guid isPermaLink="false">${escapeXml(i.guid)}</guid>`,
		i.pubDate ? `<pubDate>${escapeXml(i.pubDate)}</pubDate>` : "",
		i.creator ? `<dc:creator>${escapeXml(i.creator)}</dc:creator>` : "",
		`<description>${escapeXml(i.description || "")}</description>`,
		i.contentHtml ? `<content:encoded>${cdata(i.contentHtml)}</content:encoded>` : "",
		"</item>",
	]
		.filter(Boolean)
		.join("\n");
}

function buildRss(opts: {
	title: string;
	link: string;
	selfUrl: string;
	description: string;
	items: FeedItem[];
}): string {
	return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>${escapeXml(opts.title)}</title>
<link>${escapeXml(opts.link)}</link>
<atom:link href="${escapeXml(opts.selfUrl)}" rel="self" type="application/rss+xml"/>
<description>${escapeXml(opts.description)}</description>
<generator>Freedium</generator>
${opts.items.map(renderItem).join("\n")}
</channel>
</rss>`;
}

function toUtc(v: string | number | undefined | null): string {
	if (!v) return "";
	const d = new Date(v);
	return isNaN(d.getTime()) ? "" : d.toUTCString();
}

async function mapLimit<T, R>(
	items: T[],
	limit: number,
	fn: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
	const out: R[] = new Array(items.length);
	let next = 0;
	async function worker() {
		while (next < items.length) {
			const i = next++;
			out[i] = await fn(items[i], i);
		}
	}
	await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
	return out;
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
	return Promise.race([
		p,
		new Promise<T>((_, rej) => setTimeout(() => rej(new Error("timeout")), ms)),
	]);
}

// ── A: recently-unlocked feed ────────────────────────────────────────────────
async function recentFeed(selfUrl: string, fetchFn: typeof fetch): Promise<string> {
	const res = await fetchFn(`${config.API_URL}/articles/recent?limit=30`);
	const posts: Array<Record<string, unknown>> = res.ok ? (await res.json()).posts || [] : [];
	const items: FeedItem[] = posts.map((p) => ({
		title: String(p.title || "Untitled"),
		link: `${config.SITE_URL}/${p.medium_url || ""}`,
		guid: String(p.post_id || p.medium_url || ""),
		pubDate: toUtc((p.unlocked_at as number) || (p.first_published_at as number)),
		creator: String(p.creator_name || ""),
		description: String(p.subtitle || ""),
	}));
	return buildRss({
		title: "Freedium — Recently Unlocked",
		link: config.SITE_URL,
		selfUrl,
		description: "Articles recently read paywall-free through Freedium.",
		items,
	});
}

// ── B: proxy an external feed, inline full content ───────────────────────────
async function proxyFeed(
	feedUrl: string,
	selfUrl: string,
	fetchFn: typeof fetch,
): Promise<string> {
	let parsed: URL;
	try {
		parsed = new URL(feedUrl);
	} catch {
		throw error(400, "invalid url");
	}
	if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
		throw error(400, "unsupported protocol");
	}
	if (!HOST_ALLOW.test(parsed.hostname)) {
		throw error(400, "feed host not allowed (medium.com / nytimes.com only)");
	}

	let src: Response;
	try {
		src = await fetchFn(feedUrl, {
			signal: AbortSignal.timeout(15_000),
			headers: { "user-agent": "Freedium RSS" },
		});
	} catch {
		throw error(502, "could not fetch source feed");
	}
	if (!src.ok) throw error(502, `source feed returned ${src.status}`);

	const feed = await new Parser().parseString(await src.text());
	const entries = (feed.items || []).slice(0, MAX_ITEMS);

	const items = await mapLimit(entries, RENDER_CONCURRENCY, async (e) => {
		const articleUrl = (e.link || "").trim();
		let host = "";
		try {
			host = new URL(articleUrl).hostname;
		} catch {
			return null;
		}
		const supported = HOST_ALLOW.test(host);
		const link = supported ? `${config.SITE_URL}/${articleUrl}` : articleUrl;

		let contentHtml = "";
		if (supported) {
			try {
				const r = await withTimeout(
					renderArticle(articleUrl, { mode: "web" }),
					PER_ITEM_TIMEOUT_MS,
				);
				if (r?.html) contentHtml = absolutize(r.html);
			} catch {
				// render failed/timed out → item stays link-only
			}
		}
		return {
			title: e.title || "Untitled",
			link,
			guid: articleUrl || e.guid || link,
			pubDate: toUtc(e.isoDate || e.pubDate),
			creator: (e as { creator?: string }).creator || "",
			description: e.contentSnippet || "",
			contentHtml,
		} as FeedItem;
	});

	return buildRss({
		title: `${feed.title || "Feed"} — via Freedium`,
		link: feed.link || config.SITE_URL,
		selfUrl,
		description: feed.description || "Paywall-free via Freedium.",
		items: items.filter((i): i is FeedItem => i !== null),
	});
}

export const GET: RequestHandler = async ({ url, fetch }) => {
	const feedUrl = url.searchParams.get("url");
	const selfUrl = `${config.SITE_URL}/rss${url.search}`;
	const xml = feedUrl
		? await proxyFeed(feedUrl, selfUrl, fetch)
		: await recentFeed(selfUrl, fetch);
	return new Response(xml, {
		headers: {
			"content-type": "application/rss+xml; charset=utf-8",
			"cache-control": "public, max-age=900",
		},
	});
};
