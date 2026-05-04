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
