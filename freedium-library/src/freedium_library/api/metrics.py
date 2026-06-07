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


# `freedium_article_render_total` outcomes intentionally differ from
# the frontend's `freedium_web_article_fetch_total` outcomes:
#
#   Backend (here): success | parser_failure | upstream_4xx | upstream_5xx | network_error
#   Frontend:       success | upstream_error | network_fail | not_found
#
# The backend tracks render-level distinctions visible to the FastAPI
# handler (parser fail vs Medium 4xx vs 5xx). The frontend tracks
# SSR-fetch-level distinctions visible to SvelteKit's loader.
# Operators correlating spikes across the two metrics should expect
# a 1-to-many mapping, not a name match.
ARTICLE_RENDER = _MetricPair(
    counter=Counter(
        "freedium_article_render_total",
        "Article render attempts, labelled by outcome.",
        labelnames=("outcome",),
    ),
    histogram=Histogram(
        "freedium_article_render_duration_seconds",
        "Article render latency in seconds.",
        # Extend past 10s: cold renders (Medium fetch + render through WARP)
        # take 10-90s. Default buckets top at 10, pinning p99 at the ceiling.
        buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
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

CACHE_HITS = Counter(
    "freedium_cache_hits_total",
    "Post-cache lookups served from Mongo without hitting Medium.",
)

CACHE_MISSES = Counter(
    "freedium_cache_misses_total",
    "Post-cache lookups that fell through to Medium.",
)

RENDERED_CACHE_HITS = Counter(
    "freedium_rendered_cache_hits_total",
    "Requests served from the rendered-output cache (skipping render entirely).",
)

RENDERED_CACHE_MISSES = Counter(
    "freedium_rendered_cache_misses_total",
    "Requests that missed the rendered-output cache and required a full render.",
)

# PNG → JXL image conversion pipeline (background worker, every 2 min)
JXL_CONVERSION = Counter(
    "freedium_jxl_conversion_total",
    "PNG → JXL conversions by the background worker, labelled by outcome.",
    labelnames=("outcome",),
)  # outcomes: success | cjxl_timeout | cjxl_error | size_anomaly

JXL_CONVERSION_DURATION = Histogram(
    "freedium_jxl_conversion_duration_seconds",
    "cjxl subprocess wall time per image.",
    buckets=(0.5, 1, 2, 5, 10, 30, 60),
)

JXL_SERVE = Counter(
    "freedium_jxl_serve_total",
    "Image serve format when a JXL-stored image is requested, labelled by format.",
    labelnames=("format",),
)  # formats: jxl | jpeg_fallback | fallback_error

IMAGE_SERVE = Counter(
    "freedium_image_serve_total",
    "Total image cache hits by served format (stackable to compare raw vs JXL).",
    labelnames=("format",),
)  # formats: png | jpeg | gif | webp | jxl_native | jxl_fallback


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
