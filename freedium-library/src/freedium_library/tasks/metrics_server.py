"""Tiny HTTP server exposing Prometheus /metrics for the worker process.

The worker emits conversion counters (JXL_CONVERSION, etc.) to the
default registry. Without this server, Prometheus can only scrape the
backend's /metrics — which can't see worker-side counters because the
two processes run in separate containers and the multiprocess directory
isn't shared. This gives Prometheus a second scrape target.
"""
from __future__ import annotations

import threading

from prometheus_client import REGISTRY, generate_latest


def start_metrics_server(port: int = 8079) -> None:
    """Start a minimal HTTP server on `port` that responds with Prometheus
    text on GET /metrics from the default registry. Runs in a daemon
    thread — dies when the worker process exits."""
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/metrics", "/healthz"):
                data = generate_latest(REGISTRY)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()

    server = HTTPServer(("0.0.0.0", port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

