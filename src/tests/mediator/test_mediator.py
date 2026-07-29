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

"""Tests for the mediator module."""

import base64
import json
from unittest import mock

import pytest

from mediator import mediator


def _encoded_result(output_files, task_files=None):
    """Base64-encode the dict the mediator expects from a Celery task."""
    payload = {
        "output_files": output_files,
        "task_files": task_files or [],
        "file_reports": [],
        "task_report": None,
        "workflow_id": 1,
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


@pytest.fixture
def fake_dependencies(monkeypatch):
    """Stub the DB/hash/report helpers so the test doesn't need real infra."""
    created = []

    def _fake_create_file_in_database(db, file_data, result_dict, db_task):
        created.append(file_data.get("uuid"))
        fake = mock.Mock()
        fake.id = len(created)
        return fake

    monkeypatch.setattr(
        mediator, "create_file_in_database", _fake_create_file_in_database
    )
    monkeypatch.setattr(mediator, "process_pending_file_reports", mock.Mock())
    monkeypatch.setattr(mediator, "generate_hashes", mock.Mock())
    monkeypatch.setattr(mediator, "create_task_report_in_db", mock.Mock())

    return created


def _run_process_successful_task(monkeypatch, encoded_result):
    """Invoke process_successful_task with the given encoded Celery result."""
    mock_async_result = mock.Mock()
    mock_async_result.get.return_value = encoded_result
    monkeypatch.setattr(mediator, "AsyncResult", lambda *a, **kw: mock_async_result)

    celery_task = mock.Mock(uuid="task-uuid")
    db_task = mock.Mock()
    mediator.process_successful_task(
        db=mock.Mock(), celery_task=celery_task, db_task=db_task, celery_app=mock.Mock()
    )


def test_output_file_with_register_in_db_false_is_skipped(
    monkeypatch, fake_dependencies
):
    """Files with register_in_db=False must not be registered in the DB."""
    output_files = [
        {"uuid": "keep-me", "register_in_db": True},
        {"uuid": "skip-me", "register_in_db": False},
    ]
    _run_process_successful_task(monkeypatch, _encoded_result(output_files))

    assert fake_dependencies == ["keep-me"]


def test_output_file_without_flag_defaults_to_registering(
    monkeypatch, fake_dependencies
):
    """Backward compat: missing flag => register (older workers keep working)."""
    output_files = [{"uuid": "legacy-file"}]
    _run_process_successful_task(monkeypatch, _encoded_result(output_files))

    assert fake_dependencies == ["legacy-file"]


def test_all_files_registered_when_all_flags_true(monkeypatch, fake_dependencies):
    output_files = [
        {"uuid": "a", "register_in_db": True},
        {"uuid": "b", "register_in_db": True},
    ]
    _run_process_successful_task(monkeypatch, _encoded_result(output_files))

    assert fake_dependencies == ["a", "b"]


def test_get_task_from_db_found(monkeypatch):
    mock_db = mock.Mock()
    mock_get = mock.Mock(return_value="mock_task")
    monkeypatch.setattr(mediator, "get_task_by_uuid_from_db", mock_get)

    result = mediator.get_task_from_db(mock_db, "test-uuid")

    assert result == "mock_task"
    mock_get.assert_called_once_with(mock_db, "test-uuid")


def test_get_task_from_db_retry_success(monkeypatch):
    mock_db = mock.Mock()
    mock_get = mock.Mock(side_effect=[None, None, "mock_task"])
    monkeypatch.setattr(mediator, "get_task_by_uuid_from_db", mock_get)
    monkeypatch.setattr(mediator.time, "sleep", mock.Mock())

    result = mediator.get_task_from_db(mock_db, "test-uuid")

    assert result == "mock_task"
    assert mock_get.call_count == 3
    mediator.time.sleep.assert_called_with(mediator.DATABASE_LOOKUP_RETRY_DELAY_SECONDS)


def test_get_task_from_db_failure(monkeypatch):
    mock_db = mock.Mock()
    mock_get = mock.Mock(return_value=None)
    monkeypatch.setattr(mediator, "get_task_by_uuid_from_db", mock_get)
    monkeypatch.setattr(mediator.time, "sleep", mock.Mock())

    result = mediator.get_task_from_db(mock_db, "test-uuid")

    assert result is None
    assert mock_get.call_count == mediator.MAX_DATABASE_LOOKUP_RETRIES


def test_update_database():
    mock_db = mock.Mock()
    mock_instance = mock.Mock()

    mediator.update_database(mock_db, mock_instance)

    mock_db.add.assert_called_once_with(mock_instance)
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once_with(mock_instance)


def test_process_failed_task():
    mock_db = mock.Mock()
    mock_celery_task = mock.Mock()
    mock_celery_task.info.return_value = {"exception": "Test Exception"}
    mock_celery_task.traceback = "Test Traceback"
    mock_db_task = mock.Mock()

    mediator.process_failed_task(mock_db, mock_celery_task, mock_db_task)

    assert mock_db_task.error_exception == "Test Exception"
    assert mock_db_task.error_traceback == "Test Traceback"


def test_create_file_in_database(monkeypatch):
    mock_db = mock.Mock()
    file_data = {
        "display_name": "test_file.txt",
        "data_type": "text:plain",
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "extension": ".txt",
        "original_path": "/tmp/test_file.txt",
        "source_file_id": 10,
    }
    task_result_dict = {"workflow_id": 42}
    db_task = mock.Mock(id=99)

    mock_workflow = mock.Mock()
    mock_workflow.folder.id = 1
    mock_workflow.user.id = 2

    mock_get_workflow = mock.Mock(return_value=mock_workflow)
    monkeypatch.setattr(mediator, "get_workflow_from_db", mock_get_workflow)

    mock_created_file = mock.Mock()
    mock_create_file = mock.Mock(return_value=mock_created_file)
    monkeypatch.setattr(mediator, "create_file_in_db", mock_create_file)

    result = mediator.create_file_in_database(
        db=mock_db,
        file_data=file_data,
        task_result_dict=task_result_dict,
        db_task=db_task,
    )

    assert result == mock_created_file
    mock_get_workflow.assert_called_once_with(mock_db, 42)

    mock_create_file.assert_called_once()
    args, _ = mock_create_file.call_args
    assert args[0] == mock_db

    file_create = args[1]
    assert file_create.display_name == "test_file.txt"
    assert file_create.filename == "test_file.txt"
    assert file_create.extension == "txt"
    assert file_create.data_type == "text:plain"
    assert str(file_create.uuid) == "123e4567-e89b-12d3-a456-426614174000"
    assert file_create.original_path == "/tmp/test_file.txt"
    assert file_create.source_file_id == 10
    assert file_create.folder_id == 1
    assert file_create.user_id == 2
    assert file_create.task_output_id == 99

    assert args[2] == mock_workflow.user


def test_create_or_defer_file_report_success(monkeypatch):
    mock_db = mock.Mock()
    mock_get_file = mock.Mock(return_value=mock.Mock())
    monkeypatch.setattr(mediator, "get_file_by_uuid_from_db", mock_get_file)

    mock_create = mock.Mock()
    monkeypatch.setattr(mediator, "create_file_report_in_db", mock_create)

    # Ensure global state is clean
    monkeypatch.setattr(mediator, "PENDING_FILE_REPORTS", {})

    file_report = {
        "input_file_uuid": "uuid-1",
        "content_file_uuid": "uuid-2",
        "summary": "Test Summary",
        "priority": 1,
    }

    mediator.create_or_defer_file_report(mock_db, file_report, 123)

    assert mock_get_file.call_count == 2
    mock_create.assert_called_once()

    args, _ = mock_create.call_args
    assert args[0] == mock_db
    assert args[1].summary == "Test Summary"
    assert args[1].input_file_uuid == "uuid-1"
    assert args[1].content_file_uuid == "uuid-2"
    assert args[2] == 123
    assert len(mediator.PENDING_FILE_REPORTS) == 0


def test_create_or_defer_file_report_deferred(monkeypatch):
    mock_db = mock.Mock()
    mock_get_file = mock.Mock(return_value=None)
    monkeypatch.setattr(mediator, "get_file_by_uuid_from_db", mock_get_file)

    mock_create = mock.Mock()
    monkeypatch.setattr(mediator, "create_file_report_in_db", mock_create)

    monkeypatch.setattr(mediator, "PENDING_FILE_REPORTS", {})

    file_report = {
        "input_file_uuid": "uuid-1",
        "content_file_uuid": "uuid-2",
        "summary": "Test Summary",
        "priority": 1,
    }

    mediator.create_or_defer_file_report(mock_db, file_report, 123)

    assert mock_get_file.call_count == 2
    assert not mock_create.called

    assert "uuid-1" in mediator.PENDING_FILE_REPORTS
    assert "uuid-2" in mediator.PENDING_FILE_REPORTS

    assert mediator.PENDING_FILE_REPORTS["uuid-1"] == [(file_report, 123)]
    assert mediator.PENDING_FILE_REPORTS["uuid-2"] == [(file_report, 123)]
