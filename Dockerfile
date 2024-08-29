# The build image
FROM python:3.12-slim-bookworm AS builder

# Install and configure poetry
RUN pip install poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

# Copy files needed to build
COPY pyproject.toml poetry.lock ./
RUN touch README.md

# Install all dependencies
RUN poetry install --without dev --no-root && rm -rf $POETRY_CACHE_DIR

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

# Set workdir for Uvicorn to function
WORKDIR /app/openrelik
