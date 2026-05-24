"""End-to-end: a failing render must increment the counter AND write a JSONL line."""
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from freedium_library.api.handlers.conftest import read_errored_links


@pytest.fixture
def app_with_temp_log(
    errored_links_jsonl: Path,
) -> Iterator[tuple[TestClient, Path]]:
    # TestClient must be entered as a context manager so the FastAPI
    # lifespan runs and populates app.state.service_resolver. Without
    # that, /api/render raises 500 from a missing-state AttributeError
    # before the resolver has a chance to raise ServiceResolutionError.
    from freedium_library.api.app import create_application
    app = create_application()
    with TestClient(app) as client:
        yield client, errored_links_jsonl


def test_unknown_service_returns_404_and_records_errored_link(
    app_with_temp_log: tuple[TestClient, Path],
) -> None:
    client, jsonl = app_with_temp_log
    res = client.post(
        "/api/render",
        json={"content": "https://example-not-a-known-service.test/x"},
    )
    assert res.status_code == 404

    metrics = client.get("/metrics").text
    # Tightened: assert THIS test's POST registered, not just that some
    # errored-link sample exists in the registry (which warmup or other
    # tests could also produce).
    assert (
        'freedium_errored_links_total{host="example-not-a-known-service.test",kind="parser_failure"}'
        in metrics
    )

    rows = read_errored_links(jsonl)
    assert any(
        r["record"]["extra"]["url"].startswith("https://example-not-a-known-service")
        for r in rows
    )
