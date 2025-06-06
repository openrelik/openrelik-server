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


def test_healthz_success(fastapi_test_client, mocker):
    """Test healthz endpoint when all services are reachable."""
    mocker.patch("healthz._check_postgresql_connection", return_value="Ok")
    mocker.patch("healthz._check_redis_connection", return_value="Ok")

    response = fastapi_test_client.get(f"/healthz")
    assert response.status_code == 200
    assert response.json() == {"postgresql": "Ok", "redis": "Ok"}


def test_healthz_postgresql_failure(fastapi_test_client, mocker):
    """Test healthz endpoint when PostgreSQL connection fails."""
    mocker.patch(
        "healthz._check_postgresql_connection",
        return_value="Database connection error",
    )
    mocker.patch("healthz._check_redis_connection", return_value="Ok")

    response = fastapi_test_client.get("/healthz")

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "postgresql": "Database connection error",
        "redis": "Ok",
    }


def test_healthz_redis_failure(fastapi_test_client, mocker):
    """Test healthz endpoint when Redis connection fails."""
    mocker.patch("healthz._check_postgresql_connection", return_value="Ok")
    mocker.patch(
        "healthz._check_redis_connection", return_value="Redis connection error"
    )

    response = fastapi_test_client.get("/healthz")

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "postgresql": "Ok",
        "redis": "Redis connection error",
    }


def test_healthz_both_failures(fastapi_test_client, mocker):
    """Test healthz endpoint when both PostgreSQL and Redis connections fail."""
    mocker.patch(
        "healthz._check_postgresql_connection",
        return_value="Database connection error",
    )
    mocker.patch(
        "healthz._check_redis_connection", return_value="Redis connection error"
    )

    response = fastapi_test_client.get("/healthz")

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "postgresql": "Database connection error",
        "redis": "Redis connection error",
    }
