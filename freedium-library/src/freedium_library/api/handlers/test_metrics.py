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
