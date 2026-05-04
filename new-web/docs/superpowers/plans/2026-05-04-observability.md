# Observability Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a self-contained Prometheus + Grafana + Loki + Promtail stack covering the SvelteKit frontend and the FastAPI backend, plus structured logging of every errored Medium URL queryable from Grafana.

**Architecture:** New top-level `stack/` directory packages new-web + freedium-library + observability behind a private docker-compose network. Backend uses `prometheus-fastapi-instrumentator` for HTTP metrics + a small custom-metrics module for domain counters; frontend uses `prom-client` via SvelteKit `hooks.server.ts`. Errored URLs are written to a JSONL file by a loguru sink, tailed by Promtail, queried in Grafana via Loki.

**Tech Stack:** FastAPI, `prometheus-fastapi-instrumentator`, loguru, SvelteKit (Node adapter), `prom-client`, Prometheus 3.1, Loki 3.3, Promtail 3.3, Grafana 11.4, Docker Compose.

**Spec:** `new-web/docs/superpowers/specs/2026-05-04-observability-design.md` (commit 17e7b51).

**Working tree:** `/home/olge/SOFT/git/freedium/new-web/.worktrees/redesign/`. All paths in this plan are relative to that root.

---

## File Map

```
freedium-library/
├── pyproject.toml                                           [modify]
├── Dockerfile                                                [create]
└── src/freedium_library/api/
    ├── app.py                                                [modify]
    ├── metrics.py                                            [create]
    ├── error_log.py                                          [create]
    ├── lifespan.py                                           [modify]
    └── handlers/
        ├── render.py                                         [modify]
        ├── pdf.py                                            [modify]
        ├── test_metrics.py                                   [create]
        ├── test_error_log.py                                 [create]
        └── test_render_metrics_integration.py                [create]

new-web/
├── package.json                                              [modify]
├── svelte.config.js                                          [modify]
├── Dockerfile                                                [create]
├── .dockerignore                                             [create]
└── src/
    ├── hooks.server.ts                                       [create]
    └── lib/server/
        ├── metrics.ts                                        [create]
        ├── metrics.test.ts                                   [create]
        └── hooks.server.test.ts                              [create]

stack/                                                        [create]
├── docker-compose.yml
├── .env.example
├── README.md
├── test-stack.sh
├── prometheus/prometheus.yml
├── promtail/config.yml
├── loki/config.yml
└── grafana/
    ├── provisioning/datasources/default.yml
    ├── provisioning/dashboards/default.yml
    └── dashboards/freedium-overview.json
```

---

## Phase A — Backend instrumentation (Tasks 1-5)

### Task 1: Wire `prometheus-fastapi-instrumentator` into the FastAPI app

**Files:**
- Modify: `freedium-library/pyproject.toml` — add dep to `[project.optional-dependencies] api`
- Modify: `freedium-library/src/freedium_library/api/app.py` — instrument & expose `/metrics`

- [ ] **Step 1: Add the dependency**

Edit `freedium-library/pyproject.toml`. In the `[project.optional-dependencies]` block under `api = [...]`, append:

```toml
    "prometheus-fastapi-instrumentator>=7.0.0",
```

The block becomes:

```toml
[project.optional-dependencies]
api = [
    "slowapi>=0.1.9",
    "fastapi[standard]>=0.115.12",
    "prometheus-fastapi-instrumentator>=7.0.0",
]
```

- [ ] **Step 2: Install the new dependency into the worktree venv**

Run: `cd freedium-library && pdm install -G api`
Expected: pdm resolves and installs `prometheus-fastapi-instrumentator` and its transitive `prometheus_client` dep. No errors.

- [ ] **Step 3: Write a failing test for `/metrics`**

Create `freedium-library/src/freedium_library/api/handlers/test_metrics.py`:

```python
"""Integration tests for the /metrics Prometheus endpoint."""
from fastapi.testclient import TestClient

from freedium_library.api.app import create_application


def _client() -> TestClient:
    return TestClient(create_application())


def test_metrics_endpoint_returns_200_and_prom_text_format():
    res = _client().get("/metrics")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    # The exposition format always declares its version at the top
    assert "version=0.0.4" in res.headers["content-type"] or b"# HELP" in res.content


def test_metrics_endpoint_includes_default_http_metric():
    # Make a request first so http_requests_total has data to expose
    client = _client()
    client.get("/")  # 404 is fine, we just need traffic
    body = _client().get("/metrics").text
    assert "http_requests_total" in body
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/test_metrics.py -v`
Expected: FAIL — `/metrics` returns 404 because we haven't wired it yet.

- [ ] **Step 5: Wire the instrumentator in `app.py`**

Edit `freedium-library/src/freedium_library/api/app.py`. Add the import near the top with the other FastAPI imports:

```python
from prometheus_fastapi_instrumentator import Instrumentator
```

Inside `create_application()`, immediately before `return app`, add:

```python
    Instrumentator(
        excluded_handlers=["/metrics", "/healthz"],
        should_group_status_codes=False,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/test_metrics.py -v`
Expected: PASS — both tests green.

- [ ] **Step 7: Commit**

```bash
git add freedium-library/pyproject.toml freedium-library/pdm.lock freedium-library/src/freedium_library/api/app.py freedium-library/src/freedium_library/api/handlers/test_metrics.py
git commit -m "feat(backend): expose Prometheus /metrics endpoint"
```

---

### Task 2: Custom domain metrics module

**Files:**
- Create: `freedium-library/src/freedium_library/api/metrics.py`
- Modify: `freedium-library/src/freedium_library/api/handlers/test_metrics.py` (extend)

- [ ] **Step 1: Extend the metrics test to cover custom counters**

Append to `freedium-library/src/freedium_library/api/handlers/test_metrics.py`:

```python
def test_metrics_endpoint_includes_custom_domain_metrics():
    # Touch the metrics module so they register against the default registry
    from freedium_library.api import metrics  # noqa: F401

    body = _client().get("/metrics").text
    for name in (
        "freedium_article_render_total",
        "freedium_article_render_duration_seconds",
        "freedium_pdf_render_total",
        "freedium_pdf_render_duration_seconds",
        "freedium_errored_links_total",
    ):
        assert name in body, f"missing metric {name} in /metrics body"


def test_track_render_records_outcome_and_duration():
    from freedium_library.api.metrics import track_render, ARTICLE_RENDER

    with track_render(ARTICLE_RENDER) as ctx:
        ctx.set_outcome("success")

    body = _client().get("/metrics").text
    assert 'freedium_article_render_total{outcome="success"}' in body
    assert "freedium_article_render_duration_seconds_count" in body


def test_track_render_default_outcome_is_success_on_clean_exit():
    from freedium_library.api.metrics import track_render, PDF_RENDER

    with track_render(PDF_RENDER):
        pass  # no explicit set_outcome — should default to "success"

    body = _client().get("/metrics").text
    assert 'freedium_pdf_render_total{outcome="success"}' in body


def test_track_render_records_failure_on_exception():
    from freedium_library.api.metrics import track_render, ARTICLE_RENDER

    try:
        with track_render(ARTICLE_RENDER) as ctx:
            ctx.set_outcome("parser_failure")
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    body = _client().get("/metrics").text
    assert 'freedium_article_render_total{outcome="parser_failure"}' in body
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/test_metrics.py -v`
Expected: FAIL — `freedium_library.api.metrics` does not exist.

- [ ] **Step 3: Create the metrics module**

Create `freedium-library/src/freedium_library/api/metrics.py`:

```python
"""Custom domain metrics for Freedium.

The HTTP-level metrics (http_requests_total etc.) come from
prometheus-fastapi-instrumentator. This module owns *domain* metrics:
article rendering, PDF rendering, and errored-link counts.

Each metric name uses the `freedium_` prefix to namespace it apart from
the framework-emitted metrics.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Iterator

from prometheus_client import Counter, Histogram


@dataclass(frozen=True)
class _MetricPair:
    counter: Counter
    histogram: Histogram


ARTICLE_RENDER = _MetricPair(
    counter=Counter(
        "freedium_article_render_total",
        "Article render attempts, labelled by outcome.",
        labelnames=("outcome",),
    ),
    histogram=Histogram(
        "freedium_article_render_duration_seconds",
        "Article render latency in seconds.",
    ),
)

PDF_RENDER = _MetricPair(
    counter=Counter(
        "freedium_pdf_render_total",
        "PDF render attempts, labelled by outcome.",
        labelnames=("outcome",),
    ),
    histogram=Histogram(
        "freedium_pdf_render_duration_seconds",
        "PDF render latency in seconds.",
    ),
)

ERRORED_LINKS = Counter(
    "freedium_errored_links_total",
    "Article URLs that failed to render or fetch.",
    labelnames=("kind", "host"),
)


class _RenderContext:
    """Mutable handle yielded by track_render() so callers can set the
    outcome label explicitly (e.g., distinguishing parser_failure from
    upstream_5xx). If no outcome is set, defaults to 'success' on clean
    exit; on exception, the caller-set outcome (or 'unknown') is used."""

    def __init__(self) -> None:
        self._outcome: str | None = None

    def set_outcome(self, outcome: str) -> None:
        self._outcome = outcome

    @property
    def outcome(self) -> str | None:
        return self._outcome


@contextmanager
def track_render(metric: _MetricPair) -> Iterator[_RenderContext]:
    """Time a render block and record the outcome counter.

    Usage:
        with track_render(ARTICLE_RENDER) as ctx:
            try:
                do_work()
            except ParserError:
                ctx.set_outcome("parser_failure")
                raise

    On clean exit with no outcome set, records 'success'. On exception
    with an outcome already set, records that outcome. Always records
    the histogram observation regardless of outcome.
    """
    ctx = _RenderContext()
    start = perf_counter()
    try:
        yield ctx
    except BaseException:
        outcome = ctx.outcome or "unknown"
        metric.counter.labels(outcome=outcome).inc()
        metric.histogram.observe(perf_counter() - start)
        raise
    else:
        outcome = ctx.outcome or "success"
        metric.counter.labels(outcome=outcome).inc()
        metric.histogram.observe(perf_counter() - start)
```

- [ ] **Step 4: Ensure metrics are imported on app startup**

Edit `freedium-library/src/freedium_library/api/app.py`. Add at the top of the module (after the existing imports):

```python
from freedium_library.api import metrics as _metrics  # noqa: F401  # registers Prom metrics
```

This guarantees the metric objects are registered against the default registry before `/metrics` is first scraped.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/test_metrics.py -v`
Expected: PASS — all metric tests green.

- [ ] **Step 6: Commit**

```bash
git add freedium-library/src/freedium_library/api/metrics.py freedium-library/src/freedium_library/api/app.py freedium-library/src/freedium_library/api/handlers/test_metrics.py
git commit -m "feat(backend): add domain metrics module (article/pdf render, errored links)"
```

---

### Task 3: Errored-link writer (loguru sink + helper)

**Files:**
- Create: `freedium-library/src/freedium_library/api/error_log.py`
- Create: `freedium-library/src/freedium_library/api/handlers/test_error_log.py`
- Modify: `freedium-library/src/freedium_library/api/lifespan.py` — register sink at startup

- [ ] **Step 1: Write the failing test**

Create `freedium-library/src/freedium_library/api/handlers/test_error_log.py`:

```python
"""Tests for the errored-link JSONL writer."""
import json
from pathlib import Path

import pytest
from loguru import logger


@pytest.fixture
def jsonl_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "errored-links.jsonl"
    monkeypatch.setenv("ERROR_LOG_PATH", str(target))

    # Reset loguru, then re-register the sink against the patched env var.
    logger.remove()
    from freedium_library.api.error_log import register_error_log_sink
    register_error_log_sink()
    yield target
    logger.remove()


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_log_errored_link_writes_jsonl(jsonl_path: Path):
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("https://medium.com/@u/x", "parser_failure", None, "boom")
    rows = _read(jsonl_path)
    assert len(rows) == 1
    payload = rows[0]["record"]["extra"]
    assert payload["url"] == "https://medium.com/@u/x"
    assert payload["kind"] == "parser_failure"
    assert payload["host"] == "medium.com"
    assert payload["status"] is None
    assert payload["error"] == "boom"


def test_log_errored_link_normalizes_www_prefix(jsonl_path: Path):
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("https://www.medium.com/@u/x", "upstream_4xx", 404, "Not Found")
    payload = _read(jsonl_path)[0]["record"]["extra"]
    assert payload["host"] == "medium.com"
    assert payload["status"] == 404


def test_log_errored_link_keeps_subdomain(jsonl_path: Path):
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("https://x.medium.com/p/123", "upstream_5xx", 503, "down")
    payload = _read(jsonl_path)[0]["record"]["extra"]
    assert payload["host"] == "x.medium.com"


def test_log_errored_link_handles_malformed_url(jsonl_path: Path):
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("::not a url::", "network_error", None, "garbage in")
    payload = _read(jsonl_path)[0]["record"]["extra"]
    assert payload["host"] == "other"


def test_log_errored_link_truncates_long_error(jsonl_path: Path):
    from freedium_library.api.error_log import log_errored_link
    msg = "x" * 1000
    log_errored_link("https://medium.com/x", "parser_failure", None, msg)
    payload = _read(jsonl_path)[0]["record"]["extra"]
    assert len(payload["error"]) == 500


def test_only_errored_link_records_reach_the_jsonl(jsonl_path: Path):
    """Other loguru calls must not pollute the errored-links file."""
    logger.info("unrelated log line")
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("https://medium.com/x", "parser_failure", None, "boom")
    rows = _read(jsonl_path)
    assert len(rows) == 1
    assert rows[0]["record"]["extra"]["url"] == "https://medium.com/x"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/test_error_log.py -v`
Expected: FAIL — `freedium_library.api.error_log` does not exist.

- [ ] **Step 3: Implement the error_log module**

Create `freedium-library/src/freedium_library/api/error_log.py`:

```python
"""Errored-link logging.

Errored Medium URLs are written to a JSON-lines file (one record per
line) via a dedicated loguru sink filtered on `extra.errored_link`.
Promtail tails the file and ships records to Loki, where Grafana
queries them. The metric counter `freedium_errored_links_total` is
incremented in lockstep so both surfaces stay aligned.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from loguru import logger

from freedium_library.api.metrics import ERRORED_LINKS


_ERROR_TRUNCATE_AT = 500


def _normalize_host(url: str) -> str:
    """Return a low-cardinality host label for the given URL.

    `www.` is stripped so Grafana's host facet doesn't split medium.com
    and www.medium.com into different rows. URLs that fail to parse get
    bucketed under the literal string 'other'.
    """
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return "other"
    if not host:
        return "other"
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def register_error_log_sink() -> None:
    """Add a loguru sink that emits one JSON line per errored link.

    Idempotent enough for app startup: callers should `logger.remove()`
    only sinks they explicitly own. Reads ERROR_LOG_PATH from env,
    defaulting to /var/log/freedium/errored-links.jsonl.
    """
    path = os.environ.get("ERROR_LOG_PATH", "/var/log/freedium/errored-links.jsonl")
    logger.add(
        path,
        format="{message}",
        filter=lambda r: r["extra"].get("errored_link") is True,
        serialize=True,
        rotation="50 MB",
        retention="30 days",
        compression="gz",
        enqueue=True,
    )


def log_errored_link(
    url: str,
    kind: str,
    status: int | None,
    error_msg: str,
) -> None:
    """Record an errored Medium URL to the JSONL log AND the Prom counter.

    Args:
        url: full URL the user/frontend asked for.
        kind: one of parser_failure | upstream_4xx | upstream_5xx | pdf_failure | network_error.
        status: upstream HTTP status if applicable, else None.
        error_msg: short class+message; truncated to 500 chars.
    """
    host = _normalize_host(url)
    truncated = error_msg[:_ERROR_TRUNCATE_AT]
    logger.bind(
        errored_link=True,
        url=url,
        kind=kind,
        host=host,
        status=status,
        error=truncated,
    ).error("errored_link")
    ERRORED_LINKS.labels(kind=kind, host=host).inc()
```

- [ ] **Step 4: Wire the sink into app startup**

Edit `freedium-library/src/freedium_library/api/lifespan.py`. Add the import alongside the existing imports near the top of the file:

```python
from freedium_library.api.error_log import register_error_log_sink
```

Then, inside the `lifespan(app)` function body, add the call as the very first line — before any other startup work, so even crashes during DI wiring still log to the file:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    register_error_log_sink()
    app.state.container = api_container
    # ... rest of existing lifespan body unchanged
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/test_error_log.py -v`
Expected: PASS — all 6 errored-link tests green.

- [ ] **Step 6: Commit**

```bash
git add freedium-library/src/freedium_library/api/error_log.py freedium-library/src/freedium_library/api/handlers/test_error_log.py freedium-library/src/freedium_library/api/lifespan.py
git commit -m "feat(backend): structured errored-link logging via loguru JSONL sink"
```

---

### Task 4: Wire metrics + error logging into the article render handler

**Files:**
- Modify: `freedium-library/src/freedium_library/api/handlers/render.py`
- Create: `freedium-library/src/freedium_library/api/handlers/test_render_metrics_integration.py`

- [ ] **Step 1: Write the failing integration test**

Create `freedium-library/src/freedium_library/api/handlers/test_render_metrics_integration.py`:

```python
"""End-to-end: a failing render must increment the counter AND write a JSONL line."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from loguru import logger


@pytest.fixture
def app_with_temp_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "errored-links.jsonl"
    monkeypatch.setenv("ERROR_LOG_PATH", str(target))
    logger.remove()
    from freedium_library.api.error_log import register_error_log_sink
    register_error_log_sink()

    from freedium_library.api.app import create_application
    app = create_application()
    return TestClient(app), target


def test_unknown_service_returns_404_and_records_errored_link(app_with_temp_log):
    client, jsonl = app_with_temp_log
    res = client.post(
        "/api/render",
        json={"content": "https://example-not-a-known-service.test/x"},
    )
    assert res.status_code == 404

    metrics = client.get("/metrics").text
    assert 'freedium_errored_links_total{' in metrics

    rows = [json.loads(line) for line in jsonl.read_text().splitlines()]
    assert any(
        r["record"]["extra"]["url"].startswith("https://example-not-a-known-service")
        for r in rows
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/test_render_metrics_integration.py -v`
Expected: FAIL — `/api/render` returns 404 without recording anything.

- [ ] **Step 3: Wire the helpers into `render.py`**

Edit `freedium-library/src/freedium_library/api/handlers/render.py`. At the top, add:

```python
from freedium_library.api.error_log import log_errored_link
from freedium_library.api.metrics import ARTICLE_RENDER, track_render
```

Modify `render_universal` to wrap its body in `track_render` and call `log_errored_link` on each failure path. The existing structure is `try/except ServiceResolutionError/InvalidMediumServicePathError/Exception`. Replace the body:

```python
    with track_render(ARTICLE_RENDER) as ctx:
        try:
            resolver: ServiceResolver = http_request.app.state.service_resolver
            service_name, service = await resolver.resolve(request.content)

            if service_name == "medium" and isinstance(service, MediumService):
                if request.frontmatter:
                    markdown, metadata = (
                        await service.arender_with_frontmatter_and_metadata(request.content)
                    )
                else:
                    markdown, metadata = await service.arender_with_metadata(request.content)
                await _record_recent(http_request, metadata)
            else:
                if request.frontmatter:
                    markdown = await service.arender_with_frontmatter(request.content)
                else:
                    markdown = await service.arender(request.content)

            return RenderResponse(markdown=markdown, service=service_name)

        except ServiceResolutionError as e:
            ctx.set_outcome("parser_failure")
            log_errored_link(request.content, "parser_failure", None, str(e))
            raise HTTPException(status_code=404, detail=str(e)) from e
        except InvalidMediumServicePathError as e:
            ctx.set_outcome("parser_failure")
            log_errored_link(request.content, "parser_failure", None, str(e))
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            ctx.set_outcome("network_error")
            log_errored_link(request.content, "network_error", None, str(e))
            raise HTTPException(
                status_code=500,
                detail=f"Error rendering content: {str(e)}",
            ) from e
```

Apply the same pattern to `render_medium_post` (the legacy Medium-specific endpoint): wrap with `track_render(ARTICLE_RENDER)`, set outcome `parser_failure` on `InvalidMediumServicePathError`, call `log_errored_link(post_id, "parser_failure", None, str(e))`.

- [ ] **Step 4: Run the integration test to verify it passes**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/test_render_metrics_integration.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend test suite to catch regressions**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/ -v`
Expected: All previously-passing tests still PASS. The new tests PASS.

- [ ] **Step 6: Commit**

```bash
git add freedium-library/src/freedium_library/api/handlers/render.py freedium-library/src/freedium_library/api/handlers/test_render_metrics_integration.py
git commit -m "feat(backend): track article-render outcomes and log errored URLs"
```

---

### Task 5: Wire metrics + error logging into the PDF handler

**Files:**
- Modify: `freedium-library/src/freedium_library/api/handlers/pdf.py`
- Modify: `freedium-library/src/freedium_library/api/handlers/test_pdf.py` (extend)

- [ ] **Step 1: Extend `test_pdf.py` with a metric+log assertion**

Open `freedium-library/src/freedium_library/api/handlers/test_pdf.py`. Append:

```python
def test_pdf_failure_increments_counter_and_logs(monkeypatch, tmp_path):
    """A render that raises must bump pdf_render_total{outcome='pdf_failure'}
    and produce a JSONL line tagged kind=pdf_failure."""
    import json
    from loguru import logger
    from freedium_library.api.error_log import register_error_log_sink

    log_path = tmp_path / "errored-links.jsonl"
    monkeypatch.setenv("ERROR_LOG_PATH", str(log_path))
    logger.remove()
    register_error_log_sink()

    # Force render_pdf to raise so we exercise the error path
    def boom(_html):
        raise RuntimeError("font cache exploded")
    monkeypatch.setattr(
        "freedium_library.api.handlers.pdf.render_pdf", boom
    )

    client = _make_app(secret="real-secret")
    res = client.post(
        "/internal/pdf",
        json={"html": "<h1>hello</h1>", "filename": "x.pdf",
              "url": "https://medium.com/@u/article-x"},
        headers={"X-Internal-Secret": "real-secret"},
    )
    assert res.status_code == 502

    # Counter is exposed on /metrics — but the PDF test app mounts only
    # the PDF router, so /metrics isn't on this client. Read the JSONL
    # log instead, which is the durable surface anyway.
    rows = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert any(r["record"]["extra"]["kind"] == "pdf_failure" for r in rows)
    assert any(
        r["record"]["extra"]["url"] == "https://medium.com/@u/article-x"
        for r in rows
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/test_pdf.py -v`
Expected: FAIL — the new test expects a JSONL row that isn't being written, AND the existing `PdfRequest` model rejects the unknown `url` field.

- [ ] **Step 3: Update `PdfRequest` to accept the optional `url`**

Edit `freedium-library/src/freedium_library/api/handlers/pdf.py`. In `PdfRequest`, add the field:

```python
class PdfRequest(BaseModel):
    """Body for POST /internal/pdf."""

    html: str = Field(..., description="Self-contained HTML document to render.")
    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r'^[^\r\n"\\/]+$',
        description="Filename for Content-Disposition (no path).",
    )
    url: str | None = Field(
        default=None,
        description=(
            "Original article URL. Used only for error logging "
            "(errored-link JSONL); not validated."
        ),
    )
```

- [ ] **Step 4: Wire the helpers into the handler**

In the same file, add imports near the top:

```python
from freedium_library.api.error_log import log_errored_link
from freedium_library.api.metrics import PDF_RENDER, track_render
```

Replace the body of `_generate_pdf` so each failure path increments the counter and logs the URL:

```python
    @beartype
    async def _generate_pdf(
        req: PdfRequest,
        _: None = Depends(require_secret),
    ) -> Response:
        url = req.url or "(unknown)"
        with track_render(PDF_RENDER) as ctx:
            try:
                inlined_html = await inline_images(req.html)
            except HTTPException:
                ctx.set_outcome("pdf_failure")
                raise
            except Exception as exc:
                ctx.set_outcome("pdf_failure")
                logger.warning(f"inline_images failed: {exc!r}")
                log_errored_link(url, "pdf_failure", None, repr(exc))
                raise HTTPException(status_code=400, detail="HTML parse failed") from exc

            try:
                pdf_bytes = render_pdf(inlined_html)
            except HTTPException:
                ctx.set_outcome("pdf_failure")
                raise
            except Exception as exc:
                ctx.set_outcome("pdf_failure")
                logger.exception("WeasyPrint render failed")
                log_errored_link(url, "pdf_failure", None, repr(exc))
                raise HTTPException(status_code=502, detail="PDF render failed") from exc

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{req.filename}"',
                },
            )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd freedium-library && pdm run pytest src/freedium_library/api/handlers/test_pdf.py -v`
Expected: PASS — all PDF tests, including the new failure-path assertion, are green.

- [ ] **Step 6: Update the SvelteKit `generatePdf` Remote Function to send `url`**

Edit `new-web/src/lib/article.remote.ts`. The single call site is in the `generatePdf` command. Modify the request body to include the original article URL — `slug` *is* the URL because the SvelteKit route is `/[...slug]` and Freedium URLs are `/<medium-url>`:

```ts
        body: JSON.stringify({ html: printHtml, filename, url: slug }),
```

The full request block becomes:

```ts
    const res = await fetch(`${PDF_SERVICE_URL}/internal/pdf`, {
        method: "POST",
        headers: {
            "content-type": "application/json",
            "x-internal-secret": PDF_SERVICE_SECRET,
        },
        body: JSON.stringify({ html: printHtml, filename, url: slug }),
    });
```

- [ ] **Step 7: Commit**

```bash
git add freedium-library/src/freedium_library/api/handlers/pdf.py freedium-library/src/freedium_library/api/handlers/test_pdf.py new-web/src
git commit -m "feat(backend): track PDF-render outcomes and log errored URLs"
```

---

## Phase B — Frontend instrumentation (Tasks 6-9)

### Task 6: Switch SvelteKit to `@sveltejs/adapter-node`

**Files:**
- Modify: `new-web/package.json`
- Modify: `new-web/svelte.config.js`

- [ ] **Step 1: Install adapter-node, remove adapter-auto**

Run: `cd new-web && bun add -d @sveltejs/adapter-node && bun remove @sveltejs/adapter-auto`
Expected: `package.json` updated, `bun.lockb` updated. No errors.

- [ ] **Step 2: Update `svelte.config.js` to import the new adapter**

Edit `new-web/svelte.config.js`. Replace:

```js
import adapter from "@sveltejs/adapter-auto";
```

with:

```js
import adapter from "@sveltejs/adapter-node";
```

The rest of the file stays identical.

- [ ] **Step 3: Verify the production build still works**

Run: `cd new-web && bun run build`
Expected: SUCCESS — produces `build/` directory containing a Node.js server entrypoint (`build/index.js`).

- [ ] **Step 4: Run the existing test suite to catch regressions**

Run: `cd new-web && bun run test`
Expected: All previously-passing vitest specs PASS.

- [ ] **Step 5: Commit**

```bash
git add new-web/package.json new-web/bun.lockb new-web/svelte.config.js
git commit -m "chore(web): switch SvelteKit adapter from adapter-auto to adapter-node"
```

---

### Task 7: Frontend metrics module (`prom-client`)

**Files:**
- Create: `new-web/src/lib/server/metrics.ts`
- Create: `new-web/src/lib/server/metrics.test.ts`
- Modify: `new-web/package.json` — add `prom-client`

- [ ] **Step 1: Install prom-client**

Run: `cd new-web && bun add prom-client`
Expected: `package.json` and `bun.lockb` updated.

- [ ] **Step 2: Write the failing test**

Create `new-web/src/lib/server/metrics.test.ts`:

```ts
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
        const out = await registry.metrics();
        expect(out).toMatch(/freedium_web_article_fetch_total\{outcome="success"\} 1/);
        expect(out).toMatch(/freedium_web_article_fetch_total\{outcome="upstream_error"\} 1/);
        expect(out).toMatch(/freedium_web_article_fetch_total\{outcome="network_fail"\} 1/);
    });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd new-web && bun run test src/lib/server/metrics.test.ts`
Expected: FAIL — module `./metrics` does not exist.

- [ ] **Step 4: Implement the metrics module**

Create `new-web/src/lib/server/metrics.ts`:

```ts
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd new-web && bun run test src/lib/server/metrics.test.ts`
Expected: PASS — 4 tests green.

- [ ] **Step 6: Commit**

```bash
git add new-web/package.json new-web/bun.lockb new-web/src/lib/server/metrics.ts new-web/src/lib/server/metrics.test.ts
git commit -m "feat(web): add prom-client server registry with HTTP and article-fetch metrics"
```

---

### Task 8: `hooks.server.ts` middleware + `/metrics` endpoint

**Files:**
- Create: `new-web/src/hooks.server.ts`
- Create: `new-web/src/lib/server/hooks.server.test.ts`

- [ ] **Step 1: Write the failing test**

Create `new-web/src/lib/server/hooks.server.test.ts`:

```ts
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd new-web && bun run test src/lib/server/hooks.server.test.ts`
Expected: FAIL — `../../hooks.server` does not exist.

- [ ] **Step 3: Implement `hooks.server.ts`**

Create `new-web/src/hooks.server.ts`:

```ts
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
            headers: { "content-type": "text/plain; version=0.0.4; charset=utf-8" },
        });
    }

    const start = performance.now();
    const response = await resolve(event);
    const durationSec = (performance.now() - start) / 1000;

    recordHttp({
        method: event.request.method,
        route: event.route.id ?? "unknown",
        status: response.status,
        duration: durationSec,
    });

    return response;
};
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd new-web && bun run test src/lib/server/hooks.server.test.ts`
Expected: PASS — 3 tests green.

- [ ] **Step 5: Smoke-check the dev server**

Run: `cd new-web && bun run dev &` (in background)
Then: `curl -s http://localhost:5173/metrics | head -5`
Expected: Output begins with `# HELP process_cpu_user_seconds_total ...` (or another default-metrics HELP line). Stop the dev server when done.

- [ ] **Step 6: Commit**

```bash
git add new-web/src/hooks.server.ts new-web/src/lib/server/hooks.server.test.ts
git commit -m "feat(web): add /metrics endpoint and HTTP-duration middleware via hooks.server.ts"
```

---

### Task 9: Wire `freedium_web_article_fetch_total` into the article SSR loader

**Files:**
- Modify: `new-web/src/routes/[...slug]/+page.server.ts`

- [ ] **Step 1: Read the current loader to understand the error branches**

Run: `cat new-web/src/routes/\[...slug\]/+page.server.ts`
Note the four return shapes already present: `success` (the happy `return { ... error: null }`), `404` (`error.code === ARTICLE_NOT_FOUND`), `500` with `RENDER_ERROR`, and any unhandled exception.

- [ ] **Step 2: Modify the loader to record outcomes**

Edit `new-web/src/routes/[...slug]/+page.server.ts`. At the top of the file, add the import:

```ts
import { recordArticleFetch } from "$lib/server/metrics";
```

In the `try` block, immediately before `return { slug: params.slug, loading: false, ... error: null }`, add:

```ts
        recordArticleFetch("success");
```

In the `if (message === "ARTICLE_NOT_FOUND") { ... }` branch, immediately before that branch's `return`, add:

```ts
            recordArticleFetch("not_found");
```

In the catch-all branch (the trailing `return` after `console.error`), immediately before the return, add:

```ts
        recordArticleFetch(
            message.startsWith("UPSTREAM_") ? "upstream_error" : "network_fail",
        );
```

(The string-prefix match is conservative: today the `renderArticle` function only uses `ARTICLE_NOT_FOUND` for the 404 branch. If you grep `new-web/src/lib/server/articleRenderer.ts` and find no other named codes, the prefix match simply records `network_fail` for everything else, which is correct for v1.)

- [ ] **Step 3: Run the existing test suite to catch regressions**

Run: `cd new-web && bun run test`
Expected: All previously-passing tests still PASS.

- [ ] **Step 4: Run a manual end-to-end check**

Run: `cd new-web && bun run dev &`
Then: `curl -s http://localhost:5173/https://medium.com/@some/known-good-article > /dev/null && curl -s http://localhost:5173/metrics | grep freedium_web_article_fetch_total`
Expected: At least one `freedium_web_article_fetch_total{outcome="success"}` line. Stop the dev server.

- [ ] **Step 5: Commit**

```bash
git add new-web/src/routes/\[...slug\]/+page.server.ts
git commit -m "feat(web): record article-fetch outcomes from the SSR loader"
```

---

## Phase C — Stack & deployment (Tasks 10-15)

### Task 10: New `Dockerfile` for `freedium-library`

**Files:**
- Create: `freedium-library/Dockerfile`
- Create: `freedium-library/.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

Create `freedium-library/.dockerignore`:

```
.venv
__pycache__
*.pyc
.pytest_cache
.coverage
.mypy_cache
node_modules
build
dist
.git
test.log
```

- [ ] **Step 2: Create the Dockerfile**

Create `freedium-library/Dockerfile`:

```dockerfile
# Build the FastAPI service from a build context that includes
# freedium-library + its sibling Python packages. Used by stack/docker-compose.yml
# with `build.context: ..` so the COPYs below resolve.

FROM python:3.12-slim AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# WeasyPrint runtime deps + curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libcairo2 \
        libffi-dev \
        libjpeg-dev \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install sibling deps first (changed less often than freedium-library itself)
COPY rl_string_helper /deps/rl_string_helper
RUN pip install /deps/rl_string_helper

COPY database-lib /deps/database-lib
RUN pip install /deps/database-lib

COPY medium-parser /deps/medium-parser
RUN pip install /deps/medium-parser

# Now the service itself with its api extras
COPY freedium-library /app/freedium-library
RUN pip install "/app/freedium-library[api]"

# Errored-link log directory; mounted volume will overlay this in compose
RUN mkdir -p /var/log/freedium

ENV ERROR_LOG_PATH=/var/log/freedium/errored-links.jsonl

EXPOSE 7080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:7080/metrics > /dev/null || exit 1

CMD ["uvicorn", "freedium_library.api.app:app", "--host", "0.0.0.0", "--port", "7080", "--log-level", "warning"]
```

- [ ] **Step 3: Build the image and verify it starts**

Run: `cd /home/olge/SOFT/git/freedium/new-web/.worktrees/redesign && docker build -t freedium-backend:test -f freedium-library/Dockerfile .`
Expected: SUCCESS — image built.

Run: `docker run --rm -d --name freedium-test -p 7080:7080 freedium-backend:test`
Then: `sleep 3 && curl -fsS http://localhost:7080/metrics | head -3`
Expected: Output starts with `# HELP ...`.
Then: `docker stop freedium-test`

- [ ] **Step 4: Commit**

```bash
git add freedium-library/Dockerfile freedium-library/.dockerignore
git commit -m "build(backend): add Dockerfile producing the FastAPI service image"
```

---

### Task 11: New `Dockerfile` for `new-web`

**Files:**
- Create: `new-web/Dockerfile`
- Create: `new-web/.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

Create `new-web/.dockerignore`:

```
node_modules
build
.svelte-kit
.git
.env
.env.*
*.log
freedium_handoff
caption-fixed.png
docs
```

- [ ] **Step 2: Create the multi-stage Dockerfile**

Create `new-web/Dockerfile`:

```dockerfile
# Multi-stage Bun build for SvelteKit (adapter-node).
#
#   stage 1: install + build
#   stage 2: minimal runtime image that runs `node build/`

FROM oven/bun:1.1 AS build
WORKDIR /app

# Lockfile-only install layer for cache friendliness
COPY package.json bun.lockb ./
RUN bun install --frozen-lockfile

COPY . .
RUN bun run build

FROM oven/bun:1.1-slim AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000

# Only the runtime artefacts. node_modules ships because adapter-node
# expects them at runtime; for a smaller image consider `bun install --production`
# in build stage and copying that instead.
COPY --from=build /app/build ./build
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD wget -qO- http://localhost:3000/metrics > /dev/null || exit 1

CMD ["node", "build"]
```

- [ ] **Step 3: Build the image and verify it starts**

Run: `cd /home/olge/SOFT/git/freedium/new-web/.worktrees/redesign && docker build -t freedium-web:test -f new-web/Dockerfile new-web`
Expected: SUCCESS — image built.

Run: `docker run --rm -d --name freedium-web-test -p 3000:3000 freedium-web:test`
Then: `sleep 3 && curl -fsS http://localhost:3000/metrics | head -3`
Expected: Output starts with `# HELP ...`.
Then: `docker stop freedium-web-test`

- [ ] **Step 4: Commit**

```bash
git add new-web/Dockerfile new-web/.dockerignore
git commit -m "build(web): add multi-stage Dockerfile producing the SvelteKit Node image"
```

---

### Task 12: Prometheus, Loki, and Promtail configs

**Files:**
- Create: `stack/prometheus/prometheus.yml`
- Create: `stack/loki/config.yml`
- Create: `stack/promtail/config.yml`

- [ ] **Step 1: Prometheus scrape config**

Create `stack/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: freedium-backend
    metrics_path: /metrics
    static_configs:
      - targets: ["backend:7080"]
        labels:
          service: backend

  - job_name: freedium-web
    metrics_path: /metrics
    static_configs:
      - targets: ["web:3000"]
        labels:
          service: web

  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]
```

- [ ] **Step 2: Loki config**

Create `stack/loki/config.yml`:

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096
  log_level: warn

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2020-10-24
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  retention_period: 720h  # 30 days
  allow_structured_metadata: true

compactor:
  working_directory: /loki/compactor
  retention_enabled: true
  delete_request_store: filesystem
```

- [ ] **Step 3: Promtail config**

Create `stack/promtail/config.yml`:

```yaml
server:
  http_listen_port: 9080
  log_level: warn

positions:
  filename: /var/lib/promtail/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: freedium-errored-links
    static_configs:
      - targets: ["localhost"]
        labels:
          job: freedium
          source: errored_links
          __path__: /var/log/freedium/errored-links.jsonl

    pipeline_stages:
      # The line is loguru's serialized JSON; the real payload lives under
      # record.extra.
      - json:
          expressions:
            extra: record.extra
      - json:
          source: extra
          expressions:
            kind: kind
            host: host
            status: status
            url: url
            error: error
      - labels:
          kind:
          host:
          status:
      # Write a clean JSON line back so the URL stays queryable via |=
      - output:
          source: extra
```

- [ ] **Step 4: Commit (configs are validated together with compose in Task 14)**

```bash
git add stack/prometheus/prometheus.yml stack/loki/config.yml stack/promtail/config.yml
git commit -m "chore(stack): add Prometheus, Loki, and Promtail configurations"
```

---

### Task 13: Grafana provisioning + dashboard JSON

**Files:**
- Create: `stack/grafana/provisioning/datasources/default.yml`
- Create: `stack/grafana/provisioning/dashboards/default.yml`
- Create: `stack/grafana/dashboards/freedium-overview.json`

- [ ] **Step 1: Datasource provisioning**

Create `stack/grafana/provisioning/datasources/default.yml`:

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    uid: prometheus

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    uid: loki
```

- [ ] **Step 2: Dashboard provisioning entry**

Create `stack/grafana/provisioning/dashboards/default.yml`:

```yaml
apiVersion: 1

providers:
  - name: Default
    folder: Freedium
    type: file
    disableDeletion: false
    updateIntervalSeconds: 60
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: false
```

- [ ] **Step 3: Dashboard JSON**

Create `stack/grafana/dashboards/freedium-overview.json`:

```json
{
  "uid": "freedium-overview",
  "title": "Freedium Overview",
  "schemaVersion": 39,
  "editable": true,
  "graphTooltip": 1,
  "refresh": "30s",
  "time": { "from": "now-1h", "to": "now" },
  "templating": {
    "list": [
      {
        "name": "kind",
        "type": "query",
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "query": "label_values(freedium_errored_links_total, kind)",
        "multi": true,
        "includeAll": true,
        "current": { "text": "All", "value": "$__all" }
      },
      {
        "name": "host",
        "type": "query",
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "query": "label_values(freedium_errored_links_total, host)",
        "multi": true,
        "includeAll": true,
        "current": { "text": "All", "value": "$__all" }
      },
      {
        "name": "url",
        "type": "textbox",
        "current": { "text": "", "value": "" }
      }
    ]
  },
  "panels": [
    {
      "id": 1, "type": "stat", "title": "Total requests / min",
      "gridPos": { "x": 0, "y": 0, "w": 6, "h": 4 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "targets": [{ "expr": "sum(rate(http_requests_total[1m]))*60", "refId": "A" }],
      "fieldConfig": { "defaults": { "unit": "short" } }
    },
    {
      "id": 2, "type": "stat", "title": "Articles rendered / min",
      "gridPos": { "x": 6, "y": 0, "w": 6, "h": 4 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "targets": [{ "expr": "sum(rate(freedium_article_render_total{outcome=\"success\"}[1m]))*60", "refId": "A" }]
    },
    {
      "id": 3, "type": "stat", "title": "Error rate (5m)",
      "gridPos": { "x": 12, "y": 0, "w": 6, "h": 4 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "targets": [{
        "expr": "sum(rate(http_requests_total{status=~\"5..\"}[5m])) / sum(rate(http_requests_total[5m]))",
        "refId": "A"
      }],
      "fieldConfig": {
        "defaults": {
          "unit": "percentunit",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "red",   "value": 0.01 }
            ]
          }
        }
      }
    },
    {
      "id": 4, "type": "stat", "title": "PDFs rendered / hour",
      "gridPos": { "x": 18, "y": 0, "w": 6, "h": 4 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "targets": [{ "expr": "sum(rate(freedium_pdf_render_total{outcome=\"success\"}[5m]))*3600", "refId": "A" }]
    },
    {
      "id": 5, "type": "timeseries", "title": "HTTP latency (p50/p95/p99)",
      "gridPos": { "x": 0, "y": 4, "w": 12, "h": 8 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "targets": [
        { "expr": "histogram_quantile(0.50, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))", "legendFormat": "p50", "refId": "A" },
        { "expr": "histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))", "legendFormat": "p95", "refId": "B" },
        { "expr": "histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))", "legendFormat": "p99", "refId": "C" }
      ]
    },
    {
      "id": 6, "type": "timeseries", "title": "Article render latency",
      "gridPos": { "x": 12, "y": 4, "w": 12, "h": 8 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "targets": [
        { "expr": "histogram_quantile(0.50, sum by (le) (rate(freedium_article_render_duration_seconds_bucket[5m])))", "legendFormat": "p50", "refId": "A" },
        { "expr": "histogram_quantile(0.95, sum by (le) (rate(freedium_article_render_duration_seconds_bucket[5m])))", "legendFormat": "p95", "refId": "B" }
      ]
    },
    {
      "id": 7, "type": "timeseries", "title": "Errored links by kind",
      "gridPos": { "x": 0, "y": 12, "w": 12, "h": 8 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "targets": [{
        "expr": "sum by (kind) (rate(freedium_errored_links_total{kind=~\"$kind\",host=~\"$host\"}[1m]))",
        "legendFormat": "{{kind}}", "refId": "A"
      }],
      "fieldConfig": { "defaults": { "custom": { "stacking": { "mode": "normal" } } } }
    },
    {
      "id": 8, "type": "barchart", "title": "Top errored hosts (1h)",
      "gridPos": { "x": 12, "y": 12, "w": 12, "h": 8 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "targets": [{
        "expr": "topk(10, sum by (host) (increase(freedium_errored_links_total[1h])))",
        "refId": "A"
      }]
    },
    {
      "id": 9, "type": "logs", "title": "Recent errored URLs",
      "gridPos": { "x": 0, "y": 20, "w": 12, "h": 10 },
      "datasource": { "type": "loki", "uid": "loki" },
      "targets": [{
        "expr": "{job=\"freedium\",source=\"errored_links\",kind=~\"$kind\",host=~\"$host\"}",
        "refId": "A"
      }],
      "options": { "showTime": true, "wrapLogMessage": true }
    },
    {
      "id": 10, "type": "logs", "title": "Errored URL search ($url)",
      "gridPos": { "x": 12, "y": 20, "w": 12, "h": 10 },
      "datasource": { "type": "loki", "uid": "loki" },
      "targets": [{
        "expr": "{job=\"freedium\",source=\"errored_links\"} |= \"$url\"",
        "refId": "A"
      }],
      "options": { "showTime": true, "wrapLogMessage": true }
    }
  ]
}
```

- [ ] **Step 4: Commit**

```bash
git add stack/grafana
git commit -m "chore(stack): provision Grafana datasources + Freedium overview dashboard"
```

---

### Task 14: `docker-compose.yml`, `.env.example`, README

**Files:**
- Create: `stack/docker-compose.yml`
- Create: `stack/.env.example`
- Create: `stack/README.md`

- [ ] **Step 1: Compose file**

Create `stack/docker-compose.yml`:

```yaml
name: freedium-obs

services:
  backend:
    build:
      context: ..
      dockerfile: freedium-library/Dockerfile
    container_name: freedium-backend
    environment:
      - ERROR_LOG_PATH=/var/log/freedium/errored-links.jsonl
      - PDF_INTERNAL_SECRET=${PDF_INTERNAL_SECRET:-dev-secret-change-me}
    volumes:
      - errored_logs:/var/log/freedium
    networks:
      - freedium_obs_net
    restart: unless-stopped

  web:
    build:
      context: ../new-web
      dockerfile: Dockerfile
    container_name: freedium-web
    environment:
      - PUBLIC_API_BASE_URL=http://backend:7080
      - PDF_INTERNAL_SECRET=${PDF_INTERNAL_SECRET:-dev-secret-change-me}
    ports:
      - "${WEB_PORT:-3000}:3000"
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - freedium_obs_net
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:v3.1.0
    container_name: freedium-prometheus
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prom_data:/prometheus
    networks:
      - freedium_obs_net
    restart: unless-stopped

  loki:
    image: grafana/loki:3.3.0
    container_name: freedium-loki
    command: -config.file=/etc/loki/config.yml
    volumes:
      - ./loki/config.yml:/etc/loki/config.yml:ro
      - loki_data:/loki
    networks:
      - freedium_obs_net
    restart: unless-stopped

  promtail:
    image: grafana/promtail:3.3.0
    container_name: freedium-promtail
    command: -config.file=/etc/promtail/config.yml
    volumes:
      - ./promtail/config.yml:/etc/promtail/config.yml:ro
      - errored_logs:/var/log/freedium:ro
      - promtail_data:/var/lib/promtail
    depends_on:
      - loki
    networks:
      - freedium_obs_net
    restart: unless-stopped

  grafana:
    image: grafana/grafana:11.4.0
    container_name: freedium-grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GF_ADMIN_PASSWORD:-admin}
      - GF_USERS_DEFAULT_THEME=dark
      - GF_AUTH_ANONYMOUS_ENABLED=${GF_ANON_ENABLED:-false}
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
      - grafana_data:/var/lib/grafana
    ports:
      - "${GRAFANA_PORT:-3001}:3000"
    depends_on:
      - prometheus
      - loki
    networks:
      - freedium_obs_net
    restart: unless-stopped

networks:
  freedium_obs_net:
    driver: bridge

volumes:
  prom_data:
  loki_data:
  grafana_data:
  promtail_data:
  errored_logs:
```

- [ ] **Step 2: Environment example**

Create `stack/.env.example`:

```sh
# Copy to .env and adjust as needed.

# Grafana admin password (login: admin)
GF_ADMIN_PASSWORD=changeme

# Set to 'true' for read-only public access without login
GF_ANON_ENABLED=false

# Internal secret shared by web (Remote Function) and backend (PDF endpoint)
PDF_INTERNAL_SECRET=please-change-me

# Host port mappings
WEB_PORT=3000
GRAFANA_PORT=3001
```

- [ ] **Step 3: README**

Create `stack/README.md`:

```markdown
# Observability stack

Self-contained Docker Compose stack for the new-web frontend, the
freedium-library backend, and Prometheus + Loki + Grafana.

## One-command up

```bash
cd stack
cp .env.example .env
docker compose up -d --build
```

Open http://localhost:3001 (default password: whatever you set in
`.env` as `GF_ADMIN_PASSWORD`). The provisioned dashboard is
**Freedium / Freedium Overview**.

## What runs where

| Service     | Internal port | Host port            |
|-------------|--------------:|---------------------:|
| backend     | 7080          | —                    |
| web         | 3000          | `${WEB_PORT:-3000}`  |
| prometheus  | 9090          | —                    |
| loki        | 3100          | —                    |
| promtail    | 9080          | —                    |
| grafana     | 3000          | `${GRAFANA_PORT:-3001}` |

Only `web` and `grafana` are reachable from the host.

## Errored-link logs

The backend writes one JSON line per errored Medium URL to
`/var/log/freedium/errored-links.jsonl` inside its container. The
shared volume `errored_logs` mounts the same directory read-only into
the Promtail container, which ships records to Loki. Grafana queries
them via the dashboard's two log panels.

To tail them directly:

```bash
docker compose exec backend tail -f /var/log/freedium/errored-links.jsonl
```

## Verifying the stack

Run the smoke test:

```bash
./test-stack.sh
```

The script brings the stack up, hits a known-bad URL, asserts the
counter incremented in Prometheus and the URL reached Loki, then tears
the stack down.
```

- [ ] **Step 4: Bring the stack up and verify**

Run: `cd stack && cp .env.example .env && docker compose up -d --build`
Expected: All six containers come up; `docker compose ps` shows `(healthy)` for backend after ~30s.

Run: `curl -s http://localhost:3001/api/health | head`
Expected: JSON with `"database":"ok"`.

Run: `curl -s -G --data-urlencode 'query=up' http://localhost:9090/api/v1/query | head` *(only works if you temporarily expose Prometheus; otherwise use `docker compose exec prometheus wget -qO- http://localhost:9090/api/v1/query?query=up`).*
Expected: `up{job="freedium-backend",service="backend"}` and `up{job="freedium-web",service="web"}` both `value: 1`.

- [ ] **Step 5: Tear down and commit**

Run: `cd stack && docker compose down`

```bash
git add stack/docker-compose.yml stack/.env.example stack/README.md
git commit -m "chore(stack): docker-compose orchestration for backend, web, and observability"
```

---

### Task 15: Smoke test script

**Files:**
- Create: `stack/test-stack.sh`

- [ ] **Step 1: Write the script**

Create `stack/test-stack.sh`:

```bash
#!/usr/bin/env bash
# End-to-end smoke test for the observability stack.
#
# 1. Bring everything up.
# 2. Wait for backend health.
# 3. Hit a known-bad URL through the web.
# 4. Assert the metric incremented in Prometheus.
# 5. Assert the URL reached Loki.
# 6. Tear down (always, even on failure).

set -euo pipefail

cd "$(dirname "$0")"

cleanup() {
    docker compose down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Bringing the stack up..."
docker compose up -d --build

echo "==> Waiting for backend to become healthy..."
for i in $(seq 1 60); do
    state=$(docker inspect -f '{{.State.Health.Status}}' freedium-backend 2>/dev/null || echo "starting")
    if [[ "$state" == "healthy" ]]; then
        break
    fi
    sleep 2
done
[[ "$state" == "healthy" ]] || { echo "Backend never became healthy"; exit 1; }

BAD_URL="https://example-not-a-known-service.test/article"

echo "==> Triggering a known-bad render via the web..."
docker compose exec -T web wget -qO- "http://localhost:3000/${BAD_URL}" >/dev/null || true
sleep 5  # give Promtail time to ship the line + Prometheus time to scrape

echo "==> Asserting Prometheus saw the counter..."
result=$(docker compose exec -T prometheus wget -qO- \
    'http://localhost:9090/api/v1/query?query=freedium_errored_links_total')
echo "$result" | grep -q '"resultType":"vector"' || { echo "bad Prom response"; exit 1; }
echo "$result" | grep -q '"value"' || { echo "no errored-links samples in Prometheus"; exit 1; }

echo "==> Asserting Loki saw the URL..."
loki=$(docker compose exec -T loki wget -qO- \
    "http://localhost:3100/loki/api/v1/query?query=%7Bjob%3D%22freedium%22%2Csource%3D%22errored_links%22%7D")
echo "$loki" | grep -q "example-not-a-known-service" \
    || { echo "URL did not reach Loki"; echo "$loki" | head -c 500; exit 1; }

echo "==> SMOKE TEST PASSED"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x stack/test-stack.sh`

- [ ] **Step 3: Run it**

Run: `./stack/test-stack.sh`
Expected: Final line `==> SMOKE TEST PASSED`. Stack is torn down on exit.

- [ ] **Step 4: Commit**

```bash
git add stack/test-stack.sh
git commit -m "test(stack): end-to-end smoke test verifying the metric+log pipeline"
```

---

## Final verification

After all 15 tasks land:

- [ ] **Run the full backend test suite**

Run: `cd freedium-library && pdm run pytest -v`
Expected: All tests PASS, including the new metrics, error_log, and integration tests.

- [ ] **Run the full frontend test suite**

Run: `cd new-web && bun run test && bun run check`
Expected: All vitest specs PASS; svelte-check has 0 errors.

- [ ] **Run the smoke test once more from a clean state**

Run: `./stack/test-stack.sh`
Expected: PASSED.

- [ ] **Visually confirm the dashboard**

Run: `cd stack && docker compose up -d --build`
Open: http://localhost:3001 → Freedium / Freedium Overview
Expected: All ten panels render. Stat panels show non-zero traffic if you click around the web container at http://localhost:3000. The two log panels show real lines after triggering a bad URL.
