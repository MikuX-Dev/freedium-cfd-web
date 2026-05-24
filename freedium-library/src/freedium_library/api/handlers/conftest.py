"""Shared fixtures for handler tests.

The `errored_links_jsonl` fixture provides a tmp_path-backed loguru sink
for tests that need to inspect the errored-link JSONL emission. It also
resets Task 3's `_SINK_REGISTERED` idempotency guard so each test rebinds
the sink to its own tmp_path.

Tests using this fixture should call `flush_errored_links()` immediately
before reading the JSONL file — it wraps `logger.complete()` to flush
the `enqueue=True` background thread.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from loguru import logger


@pytest.fixture
def errored_links_jsonl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Return the path to a per-test errored-links JSONL file with the
    backend's loguru sink bound to it."""
    target = tmp_path / "errored-links.jsonl"
    monkeypatch.setenv("ERROR_LOG_PATH", str(target))

    logger.remove()
    import freedium_library.api.error_log as error_log
    error_log._SINK_REGISTERED = False
    error_log.register_error_log_sink()

    yield target

    logger.remove()
    error_log._SINK_REGISTERED = False


def flush_errored_links() -> None:
    """Flush loguru's `enqueue=True` worker thread so the JSONL file
    reflects every record written so far."""
    logger.complete()


def read_errored_links(path: Path) -> list[dict]:
    """Convenience: read a JSONL file written by the loguru sink."""
    flush_errored_links()
    return [json.loads(line) for line in path.read_text().splitlines()]
