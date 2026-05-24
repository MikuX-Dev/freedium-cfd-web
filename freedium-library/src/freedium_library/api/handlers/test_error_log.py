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
