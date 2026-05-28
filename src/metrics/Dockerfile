# The build image
FROM python:3.12-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Configure uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv_cache

WORKDIR /metrics

# Copy files needed to build
COPY pyproject.toml uv.lock ./

# Install dependencies (without dev groups)
RUN --mount=type=cache,target=/tmp/uv_cache \
    uv sync --frozen --no-dev

# The runtime image
FROM python:3.12-slim-bookworm AS runtime

# Set variables to point to the built virtualenv
ENV VIRTUAL_ENV=/metrics/.venv PATH="/metrics/.venv/bin:$PATH"

# Copy python virtualenv from the build step
WORKDIR /metrics
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Copy needed files
COPY src ./openrelik_server
COPY src/metrics/exporter.py ./openrelik_server/exporter.py

# Set workdir for the server to function
WORKDIR /metrics/openrelik_server
