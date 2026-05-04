"""End-to-end: a failing render must increment the counter AND write a JSONL line."""
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from loguru import logger


@pytest.fixture
def app_with_temp_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Path]]:
    target = tmp_path / "errored-links.jsonl"
    monkeypatch.setenv("ERROR_LOG_PATH", str(target))

    # Reset loguru sinks AND the registration guard so the sink can be re-bound
    # to the patched env var. The lifespan's register_error_log_sink() call
    # becomes a no-op once we register here, but we need to ensure each test
    # in this file gets a fresh sink pointed at its own tmp_path.
    logger.remove()
    import freedium_library.api.error_log as error_log
    error_log._SINK_REGISTERED = False
    from freedium_library.api.error_log import register_error_log_sink
    register_error_log_sink()

    # TestClient must be entered as a context manager so the FastAPI
    # lifespan runs and populates app.state.service_resolver. Without
    # that, /api/render raises 500 from a missing-state AttributeError
    # before the resolver has a chance to raise ServiceResolutionError.
    from freedium_library.api.app import create_application
    app = create_application()
    with TestClient(app) as client:
        yield client, target

    logger.remove()
    error_log._SINK_REGISTERED = False


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

    # Flush loguru's enqueue=True background thread before reading the file
    # so the JSONL reflects all records emitted up to this point.
    logger.complete()
    rows = [json.loads(line) for line in jsonl.read_text().splitlines()]
    assert any(
        r["record"]["extra"]["url"].startswith("https://example-not-a-known-service")
        for r in rows
    )
