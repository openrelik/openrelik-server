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
import pytest
from fastapi import HTTPException

import healthz


def test_healthz_success(mocker):
    """Test healthz endpoint when all services are reachable."""
    mocker.patch("healthz._check_posgresql_connection", return_value="Ok")
    mocker.patch("healthz._check_redis_connection", return_value="Ok")

    response = healthz.healthz()

    assert response == {"posgresql": "Ok", "redis": "Ok"}


def test_healthz_postgresql_failure(mocker):
    """Test healthz endpoint when PostgreSQL connection fails."""
    mocker.patch("healthz._check_posgresql_connection", return_value="Database connection error")
    mocker.patch("healthz._check_redis_connection", return_value="Ok")

    with pytest.raises(HTTPException) as exc_info:
        healthz.healthz()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {"posgresql": "Database connection error", "redis": "Ok"}


def test_healthz_redis_failure(mocker):
    """Test healthz endpoint when Redis connection fails."""
    mocker.patch("healthz._check_posgresql_connection", return_value="Ok")
    mocker.patch("healthz._check_redis_connection", return_value="Redis connection error")

    with pytest.raises(HTTPException) as exc_info:
        healthz.healthz()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {"posgresql": "Ok", "redis": "Redis connection error"}


def test_healthz_both_failures(mocker):
    """Test healthz endpoint when both PostgreSQL and Redis connections fail."""
    mocker.patch("healthz._check_posgresql_connection", return_value="Database connection error")
    mocker.patch("healthz._check_redis_connection", return_value="Redis connection error")

    with pytest.raises(HTTPException) as exc_info:
        healthz.healthz()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {"posgresql": "Database connection error", "redis": "Redis connection error"}
