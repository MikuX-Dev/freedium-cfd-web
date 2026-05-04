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
