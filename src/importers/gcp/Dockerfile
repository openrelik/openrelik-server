# The build image
FROM python:3.12-slim-bookworm AS builder

# Install and configure poetry
RUN pip install poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /importers/gcp

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
ENV VIRTUAL_ENV=/importers/gcp/.venv PATH="/importers/gcp/.venv/bin:$PATH"

# Copy python virtualenv from the build step
WORKDIR /importers/gcp
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Install additional dependencies
RUN pip install google-cloud-storage
RUN pip install google-cloud-pubsub

# Copy needed files
COPY src ./openrelik_server
COPY src/importers/gcp/importer.py ./openrelik_server/importer.py

# Set workdir for the server to function
WORKDIR /importers/gcp/openrelik_server
