"""Benchmark freedium_rust_core vs. its Python equivalents.

Usage:
    cd freedium-library
    pdm install -G bench   # one-time: installs maturin
    pdm run python ../freedium_rust_core/benchmark.py

Builds the Rust extension (release mode) into the freedium-library venv
via maturin, then runs four micro-benchmarks comparing each exported
Rust function against its Python counterpart in
freedium-library/src/freedium_library/services/medium/renderer.py.

Output is a table with per-call time, total time, and speedup ratio.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# --- 1. Build + install the Rust extension into this venv ---------

HERE = Path(__file__).resolve().parent
CARGO_TOML = HERE / "Cargo.toml"

# freedium-library is a pdm `distribution = false` project — its source
# lives at freedium-library/src/freedium_library and isn't installed
# into the venv site-packages. Add it to sys.path so we can import it.
_FL_SRC = HERE.parent / "freedium-library" / "src"
if _FL_SRC.is_dir() and str(_FL_SRC) not in sys.path:
    sys.path.insert(0, str(_FL_SRC))


def _build_rust() -> None:
    print(f"==> building freedium_rust_core (release) from {CARGO_TOML}")
    subprocess.run(
        ["maturin", "develop", "--release", "-m", str(CARGO_TOML)],
        check=True,
    )
    print("==> build OK")


def _ensure_rust_module() -> None:
    try:
        import freedium_rust_core  # noqa: F401
        # Already installed; assume up-to-date for now.
        return
    except ImportError:
        pass
    _build_rust()


# --- 2. Sample inputs ---------------------------------------------

# Representative Medium-flavored text with smart quotes, code, links.
SAMPLE_TEXT = (
    "“Hello,” she said. “It’s a wonderful day.” "
    "Visit https://medium.com/@user/article-name-12345 for more. "
    "And here’s some `inline code` with **bold** and _italic_ text. "
) * 50  # ~10KB

SAMPLE_URL = "https://medium.com/@user/article-\\(name\\)-\\[12345\\]\\\\"
SAMPLE_CODE_TEXT = "Some code with `backticks` everywhere `like` `this` " * 100

# A realistic markups payload: 20 spans of varying types
SAMPLE_MARKUPS = []
for i in range(20):
    base = i * 30
    SAMPLE_MARKUPS.append({"type": "STRONG", "start": base, "end": base + 8})
    SAMPLE_MARKUPS.append({"type": "EM", "start": base + 10, "end": base + 18})
    SAMPLE_MARKUPS.append({"type": "CODE", "start": base + 20, "end": base + 28})
SAMPLE_MARKUPS.append(
    {"type": "A", "anchorType": "LINK", "start": 0, "end": 50,
     "href": "https://medium.com/@user/article"}
)
SAMPLE_PARAGRAPH = "x" * 1000  # 1KB of text the markups address


# --- 3. Bench harness ---------------------------------------------

def _bench(name: str, fn, n_iters: int) -> dict:
    # warm up
    for _ in range(min(100, n_iters)):
        fn()
    start = time.perf_counter()
    for _ in range(n_iters):
        fn()
    elapsed = time.perf_counter() - start
    return {
        "name": name,
        "iters": n_iters,
        "total_s": elapsed,
        "per_call_us": (elapsed / n_iters) * 1_000_000,
    }


def main() -> int:
    _ensure_rust_module()
    import freedium_rust_core as rust
    from freedium_library.services.medium.renderer import (
        _escape_markdown_minimal as py_escape,
        _normalize_quotes as py_quotes,
        _unescape_markdown_url as py_unescape,
        MarkupProcessor,
    )

    # Confirm parity FIRST — if outputs differ, benchmarks are meaningless.
    print("==> parity check")
    print(f"  escape_markdown_minimal: {rust.escape_markdown_minimal(SAMPLE_CODE_TEXT[:100]) == py_escape(SAMPLE_CODE_TEXT[:100])}")
    print(f"  normalize_quotes:        {rust.normalize_quotes(SAMPLE_TEXT[:200]) == py_quotes(SAMPLE_TEXT[:200])}")
    print(f"  unescape_markdown_url:   {rust.unescape_markdown_url(SAMPLE_URL) == py_unescape(SAMPLE_URL)}")

    # MarkupProcessor: the Python class is heavier — instantiate per call to
    # mirror the per-paragraph use pattern in renderer.py.
    def py_process_markups():
        proc = MarkupProcessor(SAMPLE_PARAGRAPH, SAMPLE_MARKUPS)
        return proc.render()

    def rust_process_markups():
        return rust.process_markups(SAMPLE_PARAGRAPH, SAMPLE_MARKUPS, False)

    # We don't assert byte-equality here — the Python class may use a
    # slightly different priority / ordering rule for overlapping spans.
    print(f"  process_markups (py output, first 80 chars):   {py_process_markups()[:80]!r}")
    print(f"  process_markups (rust output, first 80 chars): {rust_process_markups()[:80]!r}")
    print()

    cases = [
        ("escape_markdown_minimal py",
            lambda: py_escape(SAMPLE_CODE_TEXT), 5000),
        ("escape_markdown_minimal rs",
            lambda: rust.escape_markdown_minimal(SAMPLE_CODE_TEXT), 5000),
        ("normalize_quotes py",
            lambda: py_quotes(SAMPLE_TEXT), 5000),
        ("normalize_quotes rs",
            lambda: rust.normalize_quotes(SAMPLE_TEXT), 5000),
        ("unescape_markdown_url py",
            lambda: py_unescape(SAMPLE_URL), 50_000),
        ("unescape_markdown_url rs",
            lambda: rust.unescape_markdown_url(SAMPLE_URL), 50_000),
        ("process_markups py", py_process_markups, 1000),
        ("process_markups rs", rust_process_markups, 1000),
    ]

    print(f"==> benchmarks")
    print(f"{'name':<32} {'iters':>10} {'total_ms':>12} {'us/call':>12}")
    print("-" * 70)
    results = {}
    for name, fn, iters in cases:
        r = _bench(name, fn, iters)
        results[name] = r
        print(f"{name:<32} {r['iters']:>10} {r['total_s']*1000:>12.2f} {r['per_call_us']:>12.2f}")

    print()
    print(f"==> speedups (rust vs python)")
    for pair in (
        ("escape_markdown_minimal", "escape_markdown_minimal py", "escape_markdown_minimal rs"),
        ("normalize_quotes",        "normalize_quotes py",        "normalize_quotes rs"),
        ("unescape_markdown_url",   "unescape_markdown_url py",   "unescape_markdown_url rs"),
        ("process_markups",         "process_markups py",         "process_markups rs"),
    ):
        py = results[pair[1]]["per_call_us"]
        rs = results[pair[2]]["per_call_us"]
        speedup = py / rs if rs > 0 else float("inf")
        print(f"  {pair[0]:<32} {speedup:>6.2f}x")

    return 0


if __name__ == "__main__":
    sys.exit(main())
