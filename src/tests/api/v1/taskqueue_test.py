# Copyright 2024 Google LLC
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

"""Tests the taskqueue endpoints."""


def test_get_registered_tasks(fastapi_test_client, mocker):
    mock_get_registered_tasks = mocker.patch("lib.celery_utils.get_registered_tasks")
    mock_get_registered_tasks.return_value = {"mock_task": "mock_details"}
    response = fastapi_test_client.get("/taskqueue/tasks/registered")
    assert response.status_code == 200
    assert response.json() == {"mock_task": "mock_details"}


def test_get_worker_stats(fastapi_test_client, mocker):
    mock_get_worker_stats = mocker.patch("lib.celery_utils.get_worker_stats")
    mock_get_worker_stats.return_value = {"worker1": {"status": "active"}}
    response = fastapi_test_client.get("/taskqueue/workers/stats/")
    assert response.status_code == 200
    assert response.json() == {"worker1": {"status": "active"}}


def test_get_worker_configs(fastapi_test_client, mocker):
    mock_get_worker_configs = mocker.patch("lib.celery_utils.get_worker_configurations")
    mock_get_worker_configs.return_value = {"worker_config_key": "value"}
    response = fastapi_test_client.get("/taskqueue/workers/configurations/")
    assert response.status_code == 200
    assert response.json() == {"worker_config_key": "value"}


def test_get_worker_reports(fastapi_test_client, mocker):
    mock_get_worker_reports = mocker.patch("lib.celery_utils.get_worker_reports")
    mock_get_worker_reports.return_value = {"worker_id": {"report_key": "report_value"}}
    response = fastapi_test_client.get("/taskqueue/workers/reports/")
    assert response.status_code == 200
    assert response.json() == {"worker_id": {"report_key": "report_value"}}


def test_ping_workers(fastapi_test_client, mocker):
    mock_ping_workers = mocker.patch("lib.celery_utils.ping_workers")

    mock_ping_workers.return_value = ["pong_worker1", "pong_worker2"]
    response = fastapi_test_client.get("/taskqueue/workers/ping/")
    assert response.status_code == 200
    assert response.json() == ["pong_worker1", "pong_worker2"]


def test_get_active_tasks(fastapi_test_client, mocker):
    mock_get_active_tasks = mocker.patch("lib.celery_utils.get_active_tasks")

    mock_get_active_tasks.return_value = {"worker1": [{"task_id": "123"}]}
    response = fastapi_test_client.get("/taskqueue/tasks/active/")
    assert response.status_code == 200
    assert response.json() == {"worker1": [{"task_id": "123"}]}


def test_get_scheduled_tasks(fastapi_test_client, mocker):
    mock_get_scheduled_tasks = mocker.patch("lib.celery_utils.get_scheduled_tasks")
    mock_get_scheduled_tasks.return_value = [{"task_id": "456", "eta": "time"}]
    response = fastapi_test_client.get("/taskqueue/tasks/scheduled/")
    assert response.status_code == 200
    assert response.json() == [{"task_id": "456", "eta": "time"}]


def test_get_reserved_tasks(fastapi_test_client, mocker):
    mock_get_reserved_tasks = mocker.patch("lib.celery_utils.get_reserved_tasks")
    mock_get_reserved_tasks.return_value = {"worker1": [{"task_id": "789"}]}
    response = fastapi_test_client.get("/taskqueue/tasks/reserved/")
    assert response.status_code == 200
    assert response.json(), {"worker1": [{"task_id": "789"}]}


def test_get_revoked_tasks(fastapi_test_client, mocker):
    mock_get_revoked_tasks = mocker.patch("lib.celery_utils.get_revoked_tasks")
    mock_get_revoked_tasks.return_value = [{"task_id": "abc", "reason": "revoked"}]
    response = fastapi_test_client.get("/taskqueue/tasks/revoked/")
    assert response.status_code == 200
    assert response.json() == [{"task_id": "abc", "reason": "revoked"}]


def test_get_active_queues(fastapi_test_client, mocker):
    mock_get_active_queues = mocker.patch("lib.celery_utils.get_active_queues")
    mock_get_active_queues.return_value = [{"name": "queue1"}]
    response = fastapi_test_client.get("/taskqueue/queues/active/")
    assert response.status_code == 200
    assert response.json() == [{"name": "queue1"}]
