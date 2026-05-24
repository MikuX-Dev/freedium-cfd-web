# freedium_rust_core

PyO3 extension exposing hot-path string processing functions from
`freedium-library`'s Medium renderer in Rust.

Exported functions:

- `escape_markdown_minimal(text: str) -> str`
- `normalize_quotes(text: str) -> str`
- `unescape_markdown_url(url: str) -> str`
- `process_markups(text: str, markups: list[dict], is_code: bool=False) -> str`

## Build

From the `freedium-library/` directory, with maturin installed:

    pdm install -G bench   # installs maturin
    pdm run maturin develop --release -m ../freedium_rust_core/Cargo.toml

This compiles a release wheel and installs it into the active venv.

## Benchmark

    pdm run python ../freedium_rust_core/benchmark.py

Compares each Rust function against its Python equivalent in
`freedium-library/src/freedium_library/services/medium/renderer.py`.

## Integration (not yet wired)

The Python renderer still owns the production path. To wire the Rust
functions in, replace the calls in `renderer.py` with `freedium_rust_core.*`
imports and add the extension build step to the backend Dockerfile.
This is a separate task.
