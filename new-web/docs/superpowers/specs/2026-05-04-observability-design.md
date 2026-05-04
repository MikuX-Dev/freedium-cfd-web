# Observability Stack — Design

**Date:** 2026-05-04
**Branch:** `feat/home-redesign`
**Status:** Approved (brainstorming)

## Goal

Add a self-contained observability stack (Prometheus + Grafana + Loki + Promtail) that surfaces traffic, latency, and error metrics for both the FastAPI backend and the SvelteKit frontend, and makes individual errored Medium URLs queryable inside Grafana.

## Why a separate stack

The existing `docker-compose/` stack at the repo root packages the **old** Jinja-based `web/` frontend together with the Python backend (root `Dockerfile` copies `./web` and the Python sibling libs into one image). The redesign replaces that frontend with `new-web/`, which has no Dockerfile and is not in any compose file today.

Rather than retrofit the legacy stack, this spec creates a parallel `stack/` directory that packages **only** `new-web/` + `freedium-library/` + observability. The legacy stack is left untouched and continues to build the old web until it is retired.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ stack/docker-compose.yml — bridge: freedium_obs_net            │
│                                                                 │
│   ┌──────────┐    ┌──────────┐                                  │
│   │ new-web  │ →  │ backend  │ ──┐                              │
│   │ :3000    │    │ :7080    │   │  /metrics scraped 15s        │
│   └────┬─────┘    └────┬─────┘   │                              │
│        │ /metrics      │         ↓                              │
│        │              JSONL → ┌────────────┐  ┌───────────┐     │
│        │              volume  │ prometheus │  │  promtail │     │
│        │                       │            │  │  (tails)  │     │
│        └─────────/metrics ─────→            │  └─────┬─────┘     │
│                                ┕━━━━━━━━━━━━┙        │ push      │
│                                       │              ↓           │
│                                       └────► ┌────────────────┐  │
│                                              │ loki :3100     │  │
│                                              └───────┬────────┘  │
│                                                      │           │
│                                              ┌───────▼────────┐  │
│                                              │ grafana :3001  │  │
│                                              │ (host port)    │  │
│                                              └────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

Only Grafana publishes a host port (`3001`). All inter-service traffic stays on the private bridge.

## Compose stack

`stack/docker-compose.yml` — five services, no profiles for v1:

| service | image / build | host port | role |
|---|---|---|---|
| `backend` | `build: ../freedium-library` | — | FastAPI + `/metrics`; writes errored-link JSONL |
| `web` | `build: ../new-web` | `3000` | SvelteKit (adapter-node) + `/metrics` |
| `prometheus` | `prom/prometheus:v3.1.0` | — | scrapes both `/metrics` every 15s |
| `loki` | `grafana/loki:3.3.0` | — | log store (filesystem, 30d retention) |
| `promtail` | `grafana/promtail:3.3.0` | — | tails errored-links JSONL → Loki |
| `grafana` | `grafana/grafana:11.4.0` | `3001` | provisioned datasources + dashboard |

**Volumes:** `prom_data`, `loki_data`, `grafana_data` (named); `errored_logs` shared between `backend` (rw) and `promtail` (ro), bind-mounted at `/var/log/freedium`.

**Networks:** single bridge `freedium_obs_net`.

## Backend instrumentation (`freedium-library`)

### Library choice

Use [`prometheus-fastapi-instrumentator`](https://github.com/trallnag/prometheus-fastapi-instrumentator). Route-template aware (bounded cardinality), exposes `/metrics` in a single line, well-maintained.

### Wiring (`api/app.py`)

```python
from prometheus_fastapi_instrumentator import Instrumentator

instrumentator = Instrumentator(
    excluded_handlers=["/metrics", "/healthz"],
    should_group_status_codes=False,
)
instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
```

This automatically emits:

- `http_requests_total{handler, method, status}`
- `http_request_duration_seconds_bucket{handler, method}`
- `http_request_size_bytes`, `http_response_size_bytes`
- inflight gauge

`handler` resolves to the FastAPI route template (e.g. `/api/article/{slug}`), never the raw URL — cardinality is bounded.

### Custom domain metrics (`api/metrics.py`)

```
freedium_article_render_total{outcome}              Counter
freedium_article_render_duration_seconds            Histogram
freedium_pdf_render_total{outcome}                  Counter
freedium_pdf_render_duration_seconds                Histogram
freedium_errored_links_total{kind, host}            Counter
```

`outcome` ∈ `{success, parser_failure, upstream_4xx, upstream_5xx, network_error}` for article render; `{success, pdf_failure}` for PDF.
`kind` ∈ `{parser_failure, upstream_4xx, upstream_5xx, pdf_failure, network_error}` (failure values only — successes don't generate errored-link entries).
`host` is `urlparse(url).hostname` lower-cased with `www.` stripped, or `other` if unparseable.

Wrapped by a `track_render(metric_pair) -> contextmanager` helper called from `articles.py` and `pdf.py` handlers. Failure paths also call the errored-link writer.

### Errored-link writer (`api/error_log.py`)

`log_errored_link(url: str, kind: str, status: int | None, error_msg: str) -> None`.

Implementation: at app startup, register a loguru sink:

```python
from loguru import logger
logger.add(
    os.environ.get("ERROR_LOG_PATH", "/var/log/freedium/errored-links.jsonl"),
    format="{message}",
    filter=lambda r: r["extra"].get("errored_link"),
    serialize=True,
    rotation="50 MB",
    retention="30 days",
    compression="gz",
)
```

Then `log_errored_link` is just:

```python
logger.bind(errored_link=True).error(
    "errored_link",
    url=url, kind=kind, host=_normalize_host(url), status=status, error=error_msg[:500],
)
```

No manual file I/O; loguru handles serialization, rotation, and compression.

### Errored-link JSONL shape

```json
{"ts":"2026-05-04T09:31:42.118Z","url":"https://medium.com/@user/slug-abc","kind":"parser_failure","host":"medium.com","status":null,"error":"KeyError: 'mediumApp'"}
```

Fields:
- `ts` — ISO-8601 UTC, ms precision (loguru `serialize=True` default).
- `url` — full Medium URL as received.
- `kind` — one of `parser_failure | upstream_4xx | upstream_5xx | pdf_failure | network_error`.
- `host` — normalized hostname (low-cardinality grouping).
- `status` — upstream HTTP status if applicable, else `null`.
- `error` — short class+message, truncated to 500 chars.

## Frontend instrumentation (`new-web`)

### Library choice

Use [`prom-client`](https://github.com/siimon/prom-client). De-facto standard Node Prometheus client.

### Adapter change

Switch `svelte.config.js` from `@sveltejs/adapter-auto` to `@sveltejs/adapter-node`. Both are existing SvelteKit deps.

### Files

`new-web/src/lib/server/metrics.ts` — module exporting:
- a singleton `Registry` with default Node metrics enabled (memory, CPU, GC).
- `freedium_web_http_requests_total{method, route, status}` — Counter.
- `freedium_web_http_request_duration_seconds{method, route}` — Histogram.
- `freedium_web_article_fetch_total{outcome}` — Counter for SSR-side article fetches in `+page.server.ts`.

`new-web/src/hooks.server.ts` — wraps `handle({ event, resolve })`:
- if `event.url.pathname === '/metrics'`: short-circuit, return `register.metrics()` with `text/plain; version=0.0.4`.
- otherwise: start timer, call `resolve(event)`, record duration + status with `event.route.id` as the `route` label (e.g. `/[...url]` — bounded cardinality).

### No frontend errored-link logging

The frontend always proxies article fetches to the backend; the backend already records errored URLs. Logging on both sides would double-count. Frontend emits only the bounded `freedium_web_article_fetch_total` counter.

## Promtail configuration

`stack/promtail/config.yml`: one scrape job tailing `/var/log/freedium/*.jsonl`. JSON pipeline stage extracts `kind`, `host`, `status` as Loki labels (low cardinality). `url` and `error` stay in the log line — queryable via Loki line filters but not promoted to labels.

## Grafana dashboard

Single provisioned dashboard `Freedium Overview` at `stack/grafana/dashboards/freedium-overview.json`, auto-loaded by `stack/grafana/provisioning/dashboards/default.yml`. Datasources `Prometheus` + `Loki` provisioned in `stack/grafana/provisioning/datasources/default.yml`.

Panels (12-col grid):

| row | panel | type | source | query (sketch) |
|---|---|---|---|---|
| 1 | Total requests/min | stat | Prom | `sum(rate(http_requests_total[1m]))*60` |
| 1 | Articles rendered/min | stat | Prom | `sum(rate(freedium_article_render_total{outcome="success"}[1m]))*60` |
| 1 | Error rate (5m) | stat (red ≥1%) | Prom | `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))` |
| 1 | PDFs rendered/hour | stat | Prom | `sum(rate(freedium_pdf_render_total{outcome="success"}[5m]))*3600` |
| 2 | HTTP latency p50/p95/p99 | timeseries | Prom | `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))` ×3 |
| 2 | Article render latency | timeseries | Prom | same shape, `freedium_article_render_duration_seconds_bucket` |
| 3 | Errored links / kind | timeseries (stacked) | Prom | `sum by (kind) (rate(freedium_errored_links_total[1m]))` |
| 3 | Errored links / host | bar chart (top-N) | Prom | `topk(10, sum by (host) (increase(freedium_errored_links_total[1h])))` |
| 4 | Recent errored URLs | logs | Loki | `{job="freedium",file=~".*errored-links.*"}` (newest 50) |
| 4 | Errored URL search | logs | Loki | same query, `$url` template variable filters via `\|= "$url"` |

Variables: `$kind` (multi-select from Prom label values), `$host` (same), `$url` (free-text, applied to Loki panel).
Defaults: time range last 1 hour, refresh 30s.

## File layout

```
stack/                                       # NEW top-level dir
├── docker-compose.yml
├── .env.example
├── README.md
├── prometheus/prometheus.yml
├── promtail/config.yml
├── loki/config.yml
└── grafana/
    ├── provisioning/datasources/default.yml
    ├── provisioning/dashboards/default.yml
    └── dashboards/freedium-overview.json

new-web/
├── Dockerfile                               # NEW: Bun → adapter-node multi-stage
├── svelte.config.js                         # adapter-auto → adapter-node
├── src/
│   ├── hooks.server.ts                      # NEW
│   └── lib/server/metrics.ts                # NEW
└── package.json                              # +prom-client, +@sveltejs/adapter-node

freedium-library/
├── Dockerfile                                # NEW
├── pyproject.toml                            # +prometheus-fastapi-instrumentator
└── src/freedium_library/api/
    ├── app.py                                # +instrumentator, +sink init
    ├── metrics.py                            # NEW
    ├── error_log.py                          # NEW
    └── handlers/{articles.py,pdf.py}         # +track_render(), +log_errored_link()
```

### Dockerfile notes

- **`freedium-library/Dockerfile`** is new. The existing root `Dockerfile` bundles old `web/` + Python and is not reusable. The new one builds the Python service from `freedium-library/` plus its sibling deps (`medium-parser`, `rl_string_helper`, `database-lib`). Compose `build.context: ..` lets it `COPY ./freedium-library` and siblings.
- **`new-web/Dockerfile`** is new. Bun multi-stage: install with `oven/bun:1.1`, run `bun run build`, copy `build/` into a slim `oven/bun:1.1-slim` runner that runs `node build`.

## Testing strategy

### Backend unit tests (`freedium-library/`)

- `test_metrics.py` — `/metrics` returns `200`, `text/plain; version=0.0.4`, contains `http_requests_total` and every custom metric name. FastAPI `TestClient`.
- `test_error_log.py` — call `log_errored_link(...)` against a `tmp_path` JSONL file (override `ERROR_LOG_PATH`), read line back, assert shape. Edge cases: `www.medium.com`, subdomain `x.medium.com`, malformed URL → `host="other"`.
- One integration test: hit a known-bad article URL with mocked render raising; assert metric counter increments AND JSONL line appears.

### Frontend unit tests (`new-web/`)

- `lib/server/metrics.test.ts` — registry exposes expected metric names; route-template labeling preserved end-to-end via mock `event`.
- `hooks.server.test.ts` — `/metrics` short-circuit returns Prom text format; non-`/metrics` requests increment counter once with route-template label.

### Stack smoke test (`stack/test-stack.sh`)

Manual / CI-optional. `docker compose up -d`, wait for both healthchecks, then:
- `curl prometheus:9090/api/v1/targets` → both targets `up`.
- Hit `web:3000/<bad-medium-url>` → `freedium_errored_links_total >= 1` AND Loki returns the URL.
- `docker compose down -v`.

Documented as the verification step in `stack/README.md`. Not in CI by default (heavy).

### Out of scope

Grafana dashboard JSON validation. Provisioning logs surface dashboard parse errors at startup; we trust that.

## Open questions

None — all decisions resolved during brainstorming.
