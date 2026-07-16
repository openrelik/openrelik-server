# The build image
FROM python:3.12-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Configure uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv_cache

WORKDIR /app

# Copy files needed to build
COPY pyproject.toml uv.lock ./

# Install dependencies (without dev groups)
RUN uv sync --locked --no-dev

# The runtime image
FROM python:3.12-slim-bookworm AS runtime

# libmagic is needed for python-magic package
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
  && rm -rf /var/lib/apt/lists/*

# Set variables to point to the built virtualenv
ENV VIRTUAL_ENV=/app/.venv PATH="/app/.venv/bin:$PATH"

# Copy python virtualenv from the build step
WORKDIR /app
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Copy needed files
COPY src ./openrelik

# Copy over DuckDB extension
COPY extras ./openrelik

# Set workdir for Uvicorn to function
WORKDIR /app/openrelik
