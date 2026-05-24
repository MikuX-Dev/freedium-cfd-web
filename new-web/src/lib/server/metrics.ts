/**
 * Server-side Prometheus registry for new-web.
 *
 * `route` labels use the SvelteKit route id (e.g. `/[...slug]`) so
 * cardinality is bounded by the route count, not by per-URL traffic.
 */
import { Counter, Histogram, Registry, collectDefaultMetrics } from "prom-client";

export const registry = new Registry();
collectDefaultMetrics({ register: registry, prefix: "" });

const httpRequests = new Counter({
	name: "freedium_web_http_requests_total",
	help: "HTTP requests handled by the SvelteKit server.",
	labelNames: ["method", "route", "status"] as const,
	registers: [registry],
});

const httpDuration = new Histogram({
	name: "freedium_web_http_request_duration_seconds",
	help: "HTTP request duration in seconds.",
	labelNames: ["method", "route"] as const,
	buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
	registers: [registry],
});

/**
 * `freedium_web_article_fetch_total` outcomes intentionally differ from
 * the backend's `freedium_article_render_total` outcomes:
 *
 *   Frontend (here):  success | upstream_error | network_fail | not_found
 *   Backend:          success | parser_failure | upstream_4xx | upstream_5xx | network_error
 *
 * The frontend tracks SSR-fetch-level distinctions visible to the
 * SvelteKit loader (did the upstream proxy fail? did SvelteKit
 * surface ARTICLE_NOT_FOUND?). The backend tracks render-level
 * distinctions visible to the FastAPI handler (did the parser fail?
 * did Medium return 4xx vs 5xx?). Operators correlating spikes
 * across the two metrics should expect a 1-to-many mapping, not
 * a name match.
 */
const articleFetch = new Counter({
	name: "freedium_web_article_fetch_total",
	help: "SSR-side article-render attempts on the frontend, by outcome.",
	labelNames: ["outcome"] as const,
	registers: [registry],
});

export type ArticleFetchOutcome =
	| "success"
	| "upstream_error"
	| "network_fail"
	| "not_found";

export function recordHttp(opts: {
	method: string;
	route: string;
	status: number;
	duration: number;
}): void {
	const route = opts.route || "unknown";
	httpRequests.labels(opts.method, route, String(opts.status)).inc();
	httpDuration.labels(opts.method, route).observe(opts.duration);
}

export function recordArticleFetch(outcome: ArticleFetchOutcome): void {
	articleFetch.labels(outcome).inc();
}
