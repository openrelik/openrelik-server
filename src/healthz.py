# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import redis
import os

from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from datastores.sql import database

router = APIRouter()


def _check_postgresql_connection() -> str:
    """Check the connection to the PostgreSQL database.

    This function uses a broad exception to catch all errors but not expose them to the
    user as this is a health check and it is unauthenticated.

    Returns:
        str: "Ok" if the connection is successful, otherwise an error message
    """
    try:
        db = database.SessionLocal()
        db.execute(text("SELECT 1"))
        return "Ok"
    except Exception:  # pylint: disable=broad-except
        return "Database connection error"


def _check_redis_connection(redis_url: str = None) -> str:
    """Check the connection to the Redis database.

    This function uses a broad exception to catch all errors but not expose them to the
    user as this is a health check and it is unauthenticated.

    Args:
        redis_url (str): The URL to the Redis database

    Returns:
        str: "Ok" if the connection is successful, otherwise an error message
    """
    if not redis_url:
        return f"Redis connection error"
    try:
        parsed_url = urlparse(redis_url)
        host = parsed_url.hostname
        port = parsed_url.port or 6379  # Default to 6379 if no port is specified
        redis_db = redis.Redis(host=host, port=port)
        redis_db.ping()
        return "Ok"
    except Exception:  # pylint: disable=broad-except
        return f"Redis connection error"


@router.get("/healthz")
def healthz() -> JSONResponse:
    """Health check endpoint.

    This endpoint checks the connection to critical services. If any of the services
    are not reachable, it will return a 500 status code with information on which
    services that are not reachable.

    Returns:
        dict: A dictionary with the status of the services

    Raises:
        HTTPException (500): If any of the services are not reachable
    """
    redis_url = os.getenv("REDIS_URL")
    status = {
        "postgresql": _check_postgresql_connection(),
        "redis": _check_redis_connection(redis_url),
    }
    # If any of the services are not reachable, return a 500 status code with the
    # status of the services that are not reachable.
    if not all(value == "Ok" for value in status.values()):
        raise HTTPException(status_code=500, detail=status)

    # If all services are reachable, return a 200 status code with the status of the
    # individual services.
    return JSONResponse(status_code=200, content=status)
