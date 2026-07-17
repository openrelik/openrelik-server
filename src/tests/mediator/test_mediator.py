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

"""Tests for the mediator's register_in_db guard in process_successful_task."""

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

    monkeypatch.setattr(mediator, "create_file_in_database", _fake_create_file_in_database)
    monkeypatch.setattr(mediator, "process_pending_file_reports", mock.Mock())
    monkeypatch.setattr(mediator, "create_task_report_in_db", mock.Mock())

    return created


def _run_process_successful_task(monkeypatch, encoded_result):
    """Invoke process_successful_task with the given encoded Celery result.

    Returns:
        The mock Celery app so callers can assert on task dispatch.
    """
    mock_async_result = mock.Mock()
    mock_async_result.get.return_value = encoded_result
    monkeypatch.setattr(mediator, "AsyncResult", lambda *a, **kw: mock_async_result)

    celery_task = mock.Mock(uuid="task-uuid")
    db_task = mock.Mock()
    celery_app = mock.Mock()
    mediator.process_successful_task(
        db=mock.Mock(), celery_task=celery_task, db_task=db_task, celery_app=celery_app
    )
    return celery_app


def test_output_file_with_register_in_db_false_is_skipped(monkeypatch, fake_dependencies):
    """Files with register_in_db=False must not be registered in the DB."""
    output_files = [
        {"uuid": "keep-me", "register_in_db": True},
        {"uuid": "skip-me", "register_in_db": False},
    ]
    _run_process_successful_task(monkeypatch, _encoded_result(output_files))

    assert fake_dependencies == ["keep-me"]


def test_output_file_without_flag_defaults_to_registering(monkeypatch, fake_dependencies):
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


def test_hashing_is_dispatched_as_background_task(monkeypatch, fake_dependencies):
    """Hashing must be dispatched to the background queue, not run inline."""
    output_files = [{"uuid": "a", "register_in_db": True}]
    task_files = [{"uuid": "log"}]

    celery_app = _run_process_successful_task(
        monkeypatch, _encoded_result(output_files, task_files=task_files)
    )

    # One dispatch for the output file (id 1) and one for the log file (id 2).
    # File ids come from the fake_dependencies fixture (len(created)).
    assert celery_app.send_task.call_count == 2
    dispatched_ids = [call.kwargs["args"][0] for call in celery_app.send_task.call_args_list]
    assert dispatched_ids == [1, 2]
    for call in celery_app.send_task.call_args_list:
        assert call.args[0] == mediator.HASHING_TASK_NAME
        assert call.kwargs["queue"] == mediator.HASHING_QUEUE_NAME
