/**
 * Global server-side hook.
 *
 * Two responsibilities:
 *   1. Expose Prometheus metrics at GET /metrics.
 *   2. Time every other request and record it against the route template.
 *
 * The route template (e.g. `/[...slug]`) is the SvelteKit route id, which
 * is bounded by the route count rather than per-URL traffic — labelling
 * by the raw pathname would explode cardinality on Freedium because
 * every Medium URL becomes its own pathname.
 */
import type { Handle } from "@sveltejs/kit";
import { registry, recordHttp } from "$lib/server/metrics";

export const handle: Handle = async ({ event, resolve }) => {
	if (event.url.pathname === "/metrics") {
		const body = await registry.metrics();
		return new Response(body, {
			status: 200,
			headers: {
				"content-type": "text/plain; version=0.0.4; charset=utf-8",
				"cache-control": "no-store",
			},
		});
	}

	const start = performance.now();
	let status = 500;
	try {
		const response = await resolve(event);
		status = response.status;
		return response;
	} finally {
		recordHttp({
			method: event.request.method,
			route: event.route.id ?? "unknown",
			status,
			duration: (performance.now() - start) / 1000,
		});
	}
};
