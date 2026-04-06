# Copyright 2026 Google LLC
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
import ast

from lib.celery_utils import (
    get_registered_tasks,
    update_task_queues,
    get_worker_stats,
    get_worker_configurations,
    get_worker_reports,
    ping_workers,
    get_active_tasks,
    get_scheduled_tasks,
    get_reserved_tasks,
    get_revoked_tasks,
    get_active_queues,
)


@pytest.fixture
def mock_celery(mocker):
    """Fixture to provide a mock Celery app."""
    return mocker.MagicMock()


def test_get_registered_tasks(mock_celery):
    """Test get_registered_tasks with valid tasks."""
    mock_inspect = mock_celery.control.inspect.return_value

    # Simulate return value from celery
    mock_inspect.registered.return_value = {
        "worker1": [
            "task.name.1 {'display_name': 'Task 1', 'description': 'Test Task'}",
            "task.name.2 {'display_name': 'Task 2'}",
        ],
        "worker2": [
            "task.name.1 {'display_name': 'Task 1', 'description': 'Test Task'}"  # Duplicate task
        ],
    }

    tasks = get_registered_tasks(mock_celery)

    assert len(tasks) == 2
    assert tasks[0]["task_name"] == "task.name.1"
    assert tasks[0]["queue_name"] == "task"
    assert tasks[0]["display_name"] == "Task 1"
    assert tasks[1]["task_name"] == "task.name.2"
    assert tasks[1]["display_name"] == "Task 2"


def test_get_registered_tasks_empty(mock_celery):
    """Test get_registered_tasks when no tasks are registered."""
    mock_inspect = mock_celery.control.inspect.return_value
    mock_inspect.registered.return_value = None

    tasks = get_registered_tasks(mock_celery)
    assert tasks == []


def test_update_task_queues(mock_celery):
    """Test update_task_queues."""
    mock_inspect = mock_celery.control.inspect.return_value

    mock_inspect.registered.return_value = {
        "worker1": [
            "task.name.1 {'display_name': 'Task 1'}",
            "other.task.2 {'display_name': 'Task 2'}",
        ]
    }

    update_task_queues(mock_celery)

    assert mock_celery.conf.task_routes == {
        "task.name.1": {"queue": "task"},
        "other.task.2": {"queue": "other"},
    }


def test_get_worker_stats(mock_celery):
    """Test get_worker_stats."""
    mock_inspect = mock_celery.control.inspect.return_value
    mock_inspect.stats.return_value = {"worker1": {"cpu": 10}}

    stats = get_worker_stats(mock_celery)
    assert stats == {"worker1": {"cpu": 10}}


def test_get_worker_configurations(mock_celery):
    """Test get_worker_configurations."""
    mock_inspect = mock_celery.control.inspect.return_value
    mock_inspect.conf.return_value = {"worker1": {"broker_url": "redis://"}}

    conf = get_worker_configurations(mock_celery)
    assert conf == {"worker1": {"broker_url": "redis://"}}


def test_get_worker_reports(mock_celery):
    """Test get_worker_reports."""
    mock_inspect = mock_celery.control.inspect.return_value
    mock_inspect.report.return_value = {"worker1": "ok"}

    report = get_worker_reports(mock_celery)
    assert report == {"worker1": "ok"}


def test_ping_workers(mock_celery):
    """Test ping_workers."""
    mock_celery.control.ping.return_value = [{"worker1": "pong"}]

    ping = ping_workers(mock_celery)
    assert ping == [{"worker1": "pong"}]


def test_get_active_tasks(mock_celery):
    """Test get_active_tasks."""
    mock_inspect = mock_celery.control.inspect.return_value
    mock_inspect.active.return_value = {"worker1": []}

    active = get_active_tasks(mock_celery)
    assert active == {"worker1": []}


def test_get_scheduled_tasks(mock_celery):
    """Test get_scheduled_tasks."""
    mock_inspect = mock_celery.control.inspect.return_value
    mock_inspect.scheduled.return_value = {"worker1": []}

    scheduled = get_scheduled_tasks(mock_celery)
    assert scheduled == {"worker1": []}


def test_get_reserved_tasks(mock_celery):
    """Test get_reserved_tasks."""
    mock_inspect = mock_celery.control.inspect.return_value
    mock_inspect.reserved.return_value = {"worker1": []}

    reserved = get_reserved_tasks(mock_celery)
    assert reserved == {"worker1": []}


def test_get_revoked_tasks(mock_celery):
    """Test get_revoked_tasks."""
    mock_inspect = mock_celery.control.inspect.return_value
    mock_inspect.revoked.return_value = {"worker1": []}

    revoked = get_revoked_tasks(mock_celery)
    assert revoked == {"worker1": []}


def test_get_active_queues(mock_celery):
    """Test get_active_queues."""
    mock_inspect = mock_celery.control.inspect.return_value
    mock_inspect.active_queues.return_value = {"worker1": []}

    queues = get_active_queues(mock_celery)
    assert queues == {"worker1": []}
