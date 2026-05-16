# Build the FastAPI service from a build context that includes
# freedium-library + its sibling Python packages. Used by stack/docker-compose.yml
# with `build.context: ..` so the COPYs below resolve.

FROM python:3.12-slim AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# WeasyPrint runtime deps + curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libcairo2 \
        libffi-dev \
        libjpeg-dev \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install sibling deps first (changed less often than freedium-library itself)
COPY rl_string_helper /deps/rl_string_helper
RUN pip install /deps/rl_string_helper

COPY database-lib /deps/database-lib
RUN pip install /deps/database-lib

COPY medium-parser /deps/medium-parser
RUN pip install /deps/medium-parser

# Now the service itself with its api extras
COPY freedium-library /app/freedium-library
RUN pip install "/app/freedium-library[api]"

# Errored-link log directory; mounted volume will overlay this in compose
RUN mkdir -p /var/log/freedium

ENV ERROR_LOG_PATH=/var/log/freedium/errored-links.jsonl

EXPOSE 7080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:7080/metrics > /dev/null || exit 1

CMD ["uvicorn", "freedium_library.api.app:app", "--host", "0.0.0.0", "--port", "7080", "--log-level", "warning"]
