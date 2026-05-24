# Multi-stage build: builder has compilers, runtime is slim.
#
# Stage 1: install dependencies (build-essential needed for Cython
# extension in rl_string_helper, libffi-dev for cryptography wheels).
# Stage 2: copy the installed site-packages into a slim runtime image
# with only WeasyPrint's *runtime* shared libraries.

FROM python:3.12-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libjpeg-dev \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install sibling deps first (cache-friendly: they change less often)
COPY rl_string_helper /deps/rl_string_helper
RUN pip install /deps/rl_string_helper

COPY database-lib /deps/database-lib
RUN pip install /deps/database-lib

COPY medium-parser /deps/medium-parser
RUN pip install /deps/medium-parser

# Now the service itself with its api extras
COPY freedium-library /app/freedium-library
RUN pip install "/app/freedium-library[api]"

# --- Build the Rust extension ---
# Install Rust toolchain via rustup into a builder-stage-only directory.
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
       | sh -s -- -y --profile minimal --default-toolchain 1.82 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir maturin

COPY freedium_rust_core /deps/freedium_rust_core
RUN cd /deps/freedium_rust_core \
    && maturin build --release --out /wheels --interpreter python3.12 \
    && pip install /wheels/freedium_rust_core-*.whl

# ---------- runtime stage ----------
FROM python:3.12-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ERROR_LOG_PATH=/var/log/freedium/errored-links.jsonl

# Runtime-only libraries: WeasyPrint shared libs + curl for healthcheck.
# build-essential and *-dev packages are deliberately omitted from this stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user
RUN useradd --system --no-create-home --shell /usr/sbin/nologin freedium \
    && mkdir -p /var/log/freedium \
    && chown freedium:freedium /var/log/freedium

# Prometheus multiprocess directory (shared across uvicorn workers)
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc
RUN mkdir -p /tmp/prometheus_multiproc && chown freedium:freedium /tmp/prometheus_multiproc

# Copy installed Python packages + console scripts from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=builder /usr/local/bin/taskiq /usr/local/bin/taskiq

USER freedium

EXPOSE 7080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:7080/healthz > /dev/null || exit 1

CMD ["uvicorn", "freedium_library.api.app:app", "--host", "0.0.0.0", "--port", "7080", "--workers", "4", "--log-level", "warning"]
