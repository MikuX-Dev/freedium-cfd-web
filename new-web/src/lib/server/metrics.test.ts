import { describe, it, expect, beforeEach } from "vitest";

describe("server metrics registry", () => {
	beforeEach(async () => {
		// Reset module state so each test sees a clean registry
		const mod = await import("./metrics");
		mod.registry.resetMetrics();
	});

	it("exposes the expected metric names in the registry", async () => {
		const { registry } = await import("./metrics");
		const names = (await registry.getMetricsAsJSON()).map((m) => m.name);
		expect(names).toContain("freedium_web_http_requests_total");
		expect(names).toContain("freedium_web_http_request_duration_seconds");
		expect(names).toContain("freedium_web_article_fetch_total");
	});

	it("includes default Node process metrics", async () => {
		const { registry } = await import("./metrics");
		const names = (await registry.getMetricsAsJSON()).map((m) => m.name);
		expect(names).toContain("process_cpu_user_seconds_total");
		expect(names).toContain("nodejs_heap_size_total_bytes");
	});

	it("recordHttp increments the counter with bounded labels", async () => {
		const { registry, recordHttp } = await import("./metrics");
		recordHttp({ method: "GET", route: "/[...slug]", status: 200, duration: 0.012 });
		const out = await registry.metrics();
		expect(out).toMatch(
			/freedium_web_http_requests_total\{method="GET",route="\/\[\.\.\.slug\]",status="200"\} 1/,
		);
	});

	it("recordArticleFetch counter accepts only known outcomes", async () => {
		const { registry, recordArticleFetch } = await import("./metrics");
		recordArticleFetch("success");
		recordArticleFetch("upstream_error");
		recordArticleFetch("network_fail");
		recordArticleFetch("not_found");
		const out = await registry.metrics();
		expect(out).toMatch(/freedium_web_article_fetch_total\{outcome="success"\} 1/);
		expect(out).toMatch(/freedium_web_article_fetch_total\{outcome="upstream_error"\} 1/);
		expect(out).toMatch(/freedium_web_article_fetch_total\{outcome="network_fail"\} 1/);
		expect(out).toMatch(/freedium_web_article_fetch_total\{outcome="not_found"\} 1/);
	});
});
