"""Errored-link AND successful-render logging.

Errored Medium URLs are written to errored-links.jsonl via a loguru sink;
successful renders are written to rendered-links.jsonl as flat JSON (one
record per line). Promtail tails both files and ships records to Loki.
The metric counter `freedium_errored_links_total` is incremented in
lockstep with errored links.
"""

from __future__ import annotations

import json
import os
import time
from urllib.parse import urlparse

from loguru import logger

from freedium_library.api.metrics import ERRORED_LINKS


_ERROR_TRUNCATE_AT = 500

_SINK_REGISTERED = False


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

    Idempotent — calling it more than once in the same process is a
    no-op. Reads ERROR_LOG_PATH from env, defaulting to
    /var/log/freedium/errored-links.jsonl.
    """
    global _SINK_REGISTERED
    if _SINK_REGISTERED:
        return
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
    _SINK_REGISTERED = True


def log_errored_link(
    url: str,
    kind: str,
    status: int | None,
    error_msg: str,
    client_ua: str = "",
) -> None:
    """Record an errored Medium URL to the JSONL log AND the Prom counter.

    Args:
        url: full URL the user/frontend asked for.
        kind: one of parser_failure | upstream_4xx | upstream_5xx | pdf_failure | network_error.
        status: upstream HTTP status if applicable, else None.
        error_msg: short class+message; truncated to 500 chars.
        client_ua: the User-Agent header from the client/frontend/bot request.
    """
    host = _normalize_host(url)
    truncated = error_msg[:_ERROR_TRUNCATE_AT]
    extra: dict[str, object] = dict(
        url=url,
        kind=kind,
        host=host,
        status=status,
        error=truncated,
    )
    if client_ua:
        extra["client_ua"] = client_ua
    logger.bind(errored_link=True, **extra).error("errored_link")  # type: ignore[arg-type]
    ERRORED_LINKS.labels(kind=kind, host=host).inc()


_RENDERED_LOG_PATH = os.environ.get(
    "RENDERED_LOG_PATH", "/var/log/freedium/rendered-links.jsonl"
)


def log_successful_render(
    url: str,
    cache_status: str,
    client_ua: str,
    render_ms: float = 0.0,
) -> None:
    """Record a successfully rendered article to rendered-links.jsonl.

    Writes a flat JSON line (no loguru wrapping) so Promtail can parse it
    with a simple `json` pipeline stage. Called from the render handler on
    every 200 response — both L2 cache hits and inline renders.
    """
    try:
        record = {
            "url": url,
            "host": _normalize_host(url),
            "status": "success",
            "cache": cache_status,
            "render_ms": int(render_ms),
            "client_ua": client_ua,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(_RENDERED_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — log failure must never break the response
        pass
