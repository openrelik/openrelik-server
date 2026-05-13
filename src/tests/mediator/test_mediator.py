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

    monkeypatch.setattr(mediator, "create_file_in_database", _fake_create_file_in_database)
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
