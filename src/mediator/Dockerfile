# The build image
FROM python:3.12-slim-bookworm as builder

# Install and configure poetry
RUN pip install poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /mediator

# Copy files needed to build
COPY pyproject.toml poetry.lock ./
RUN touch README.md

# Install all dependencies
RUN poetry install --without dev --no-root && rm -rf $POETRY_CACHE_DIR

# The runtime image
FROM python:3.12-slim-bookworm as runtime

# libmagic is needed for python-magic package
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
  && rm -rf /var/lib/apt/lists/*

# Set variables to point to the built virtualenv
ENV VIRTUAL_ENV=/mediator/.venv PATH="/mediator/.venv/bin:$PATH"

# Copy python virtualenv from the build step
WORKDIR /mediator
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Copy needed files
COPY openrelik_server ./openrelik_server
COPY openrelik_server/mediator/mediator.py ./openrelik_server/mediator.py
COPY settings.toml .

# Set workdir for the server to function
WORKDIR /mediator/openrelik_server
