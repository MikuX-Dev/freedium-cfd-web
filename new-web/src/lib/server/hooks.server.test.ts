import { describe, it, expect, beforeEach } from "vitest";

const fakeUrl = (path: string) => new URL(`http://localhost${path}`);

function makeEvent(opts: {
	pathname: string;
	method?: string;
	routeId?: string | null;
}): any {
	return {
		url: fakeUrl(opts.pathname),
		request: { method: opts.method ?? "GET" },
		route: { id: opts.routeId ?? null },
	};
}

describe("hooks.server.ts handle()", () => {
	beforeEach(async () => {
		const { registry } = await import("$lib/server/metrics");
		registry.resetMetrics();
	});

	it("short-circuits /metrics with prom text format", async () => {
		const { handle } = await import("../../hooks.server");
		const event = makeEvent({ pathname: "/metrics" });
		// resolve() must not be invoked on the metrics short-circuit
		const resolve = async () => new Response("should not be called", { status: 500 });
		const res = await handle({ event, resolve });
		expect(res.status).toBe(200);
		expect(res.headers.get("content-type")).toMatch(/text\/plain/);
		const body = await res.text();
		expect(body).toMatch(/^# HELP/m);
	});

	it("records HTTP duration for non-/metrics requests using the route id", async () => {
		const { handle } = await import("../../hooks.server");
		const { registry } = await import("$lib/server/metrics");
		const event = makeEvent({ pathname: "/some/article", routeId: "/[...slug]" });
		const resolve = async () => new Response("ok", { status: 200 });
		await handle({ event, resolve });
		const out = await registry.metrics();
		expect(out).toMatch(
			/freedium_web_http_requests_total\{method="GET",route="\/\[\.\.\.slug\]",status="200"\} 1/,
		);
	});

	it("falls back to 'unknown' route when SvelteKit could not match a route", async () => {
		const { handle } = await import("../../hooks.server");
		const { registry } = await import("$lib/server/metrics");
		const event = makeEvent({ pathname: "/no-match", routeId: null });
		const resolve = async () => new Response("nf", { status: 404 });
		await handle({ event, resolve });
		const out = await registry.metrics();
		expect(out).toMatch(/route="unknown"/);
	});
});
