"""Tests for the errored-link JSONL writer."""
from pathlib import Path

from loguru import logger

from freedium_library.api.handlers.conftest import read_errored_links


def test_log_errored_link_writes_jsonl(errored_links_jsonl: Path):
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("https://medium.com/@u/x", "parser_failure", None, "boom")
    rows = read_errored_links(errored_links_jsonl)
    assert len(rows) == 1
    payload = rows[0]["record"]["extra"]
    assert payload["url"] == "https://medium.com/@u/x"
    assert payload["kind"] == "parser_failure"
    assert payload["host"] == "medium.com"
    assert payload["status"] is None
    assert payload["error"] == "boom"


def test_log_errored_link_normalizes_www_prefix(errored_links_jsonl: Path):
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("https://www.medium.com/@u/x", "upstream_4xx", 404, "Not Found")
    payload = read_errored_links(errored_links_jsonl)[0]["record"]["extra"]
    assert payload["host"] == "medium.com"
    assert payload["status"] == 404


def test_log_errored_link_keeps_subdomain(errored_links_jsonl: Path):
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("https://x.medium.com/p/123", "upstream_5xx", 503, "down")
    payload = read_errored_links(errored_links_jsonl)[0]["record"]["extra"]
    assert payload["host"] == "x.medium.com"


def test_log_errored_link_handles_malformed_url(errored_links_jsonl: Path):
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("::not a url::", "network_error", None, "garbage in")
    payload = read_errored_links(errored_links_jsonl)[0]["record"]["extra"]
    assert payload["host"] == "other"


def test_log_errored_link_truncates_long_error(errored_links_jsonl: Path):
    from freedium_library.api.error_log import log_errored_link
    msg = "x" * 1000
    log_errored_link("https://medium.com/x", "parser_failure", None, msg)
    payload = read_errored_links(errored_links_jsonl)[0]["record"]["extra"]
    assert len(payload["error"]) == 500


def test_only_errored_link_records_reach_the_jsonl(errored_links_jsonl: Path):
    """Other loguru calls must not pollute the errored-links file."""
    logger.info("unrelated log line")
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("https://medium.com/x", "parser_failure", None, "boom")
    rows = read_errored_links(errored_links_jsonl)
    assert len(rows) == 1
    assert rows[0]["record"]["extra"]["url"] == "https://medium.com/x"


def test_log_errored_link_includes_client_ua(errored_links_jsonl: Path):
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("https://medium.com/x", "parser_failure", None, "boom",
                     client_ua="Mozilla/5.0 Bot/1.0")
    payload = read_errored_links(errored_links_jsonl)[0]["record"]["extra"]
    assert payload["client_ua"] == "Mozilla/5.0 Bot/1.0"


def test_log_errored_link_omits_empty_client_ua(errored_links_jsonl: Path):
    """An empty UA must not add a noisy client_ua="" field."""
    from freedium_library.api.error_log import log_errored_link
    log_errored_link("https://medium.com/x", "parser_failure", None, "boom")
    payload = read_errored_links(errored_links_jsonl)[0]["record"]["extra"]
    assert "client_ua" not in payload


def test_log_successful_render_writes_flat_jsonl(tmp_path, monkeypatch):
    import json
    import freedium_library.api.error_log as error_log

    target = tmp_path / "rendered-links.jsonl"
    monkeypatch.setattr(error_log, "_RENDERED_LOG_PATH", str(target))

    error_log.log_successful_render(
        "https://medium.com/@u/x", "l2_hit_cdn", "Mozilla/5.0 Chrome/131", render_ms=42.7
    )

    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert len(rows) == 1
    r = rows[0]
    assert r["url"] == "https://medium.com/@u/x"
    assert r["host"] == "medium.com"
    assert r["status"] == "success"
    assert r["cache"] == "l2_hit_cdn"
    assert r["client_ua"] == "Mozilla/5.0 Chrome/131"
    assert r["render_ms"] == 42  # int-truncated
    assert "timestamp" in r


def test_log_successful_render_never_raises(monkeypatch):
    """A log-write failure must never break the render response."""
    import freedium_library.api.error_log as error_log
    monkeypatch.setattr(error_log, "_RENDERED_LOG_PATH", "/no/such/dir/x.jsonl")
    error_log.log_successful_render("https://medium.com/x", "inline", "ua")  # no raise
