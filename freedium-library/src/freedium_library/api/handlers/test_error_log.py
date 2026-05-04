"""Tests for the errored-link JSONL writer."""
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from loguru import logger


@pytest.fixture
def jsonl_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    target = tmp_path / "errored-links.jsonl"
    monkeypatch.setenv("ERROR_LOG_PATH", str(target))

    # Reset loguru AND the registration guard so the sink can be re-bound
    # to the patched env var on each test. Production lifespan registers
    # the sink exactly once per process; the guard prevents duplicate
    # registration during uvicorn --reload or in test harnesses that
    # spin up multiple TestClient instances within one process.
    logger.remove()
    import freedium_library.api.error_log as error_log
    error_log._SINK_REGISTERED = False
    error_log.register_error_log_sink()
    yield target
    logger.remove()
    error_log._SINK_REGISTERED = False


def _read(path: Path) -> list[dict]:
    # Flush loguru's enqueue=True background thread before reading so the
    # JSONL file reflects all records emitted up to this point.
    logger.complete()
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
