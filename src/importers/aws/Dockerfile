# The build image
FROM python:3.12-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Configure uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv_cache

WORKDIR /importers/aws

# Copy files needed to build
COPY pyproject.toml uv.lock ./

# Install dependencies (without dev groups)
RUN --mount=type=cache,target=/tmp/uv_cache \
    uv sync --frozen --no-dev

# Install additional dependencies not in the server lockfile (AWS SDK + API client)
# into the same virtualenv created by `uv sync`.
ENV VIRTUAL_ENV=/importers/aws/.venv
RUN --mount=type=cache,target=/tmp/uv_cache \
    uv pip install boto3 openrelik-api-client

# The runtime image
FROM python:3.12-slim-bookworm AS runtime

# libmagic is needed for python-magic package
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
  && rm -rf /var/lib/apt/lists/*

# Set variables to point to the built virtualenv
ENV VIRTUAL_ENV=/importers/aws/.venv PATH="/importers/aws/.venv/bin:$PATH"

# Copy python virtualenv from the build step
WORKDIR /importers/aws
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Copy needed files
COPY src ./openrelik_server
COPY src/importers/aws/importer.py ./openrelik_server/importer.py

# Set workdir for the server to function
WORKDIR /importers/aws/openrelik_server
