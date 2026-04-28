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

"""Tests for the mediator's handling of the skip_file_creation flag."""

import base64
import json

import pytest

from mediator import mediator


def _encode(result_dict):
    """Encode a result dict the way workers do before publishing."""
    return base64.b64encode(json.dumps(result_dict).encode("utf-8")).decode("utf-8")


def _build_result(skip_file_creation=False, output_files=None, task_files=None):
    return {
        "output_files": output_files if output_files is not None else [{"uuid": "u1"}],
        "workflow_id": "wf-1",
        "task_files": task_files if task_files is not None else [],
        "command": "cmd",
        "meta": {},
        "file_reports": [],
        "task_report": {},
        "skip_file_creation": skip_file_creation,
    }


@pytest.fixture
def mediator_mocks(mocker):
    """Mock out all the side-effectful helpers the mediator reaches for."""
    return {
        "create_file_in_database": mocker.patch(
            "mediator.mediator.create_file_in_database"
        ),
        "process_pending_file_reports": mocker.patch(
            "mediator.mediator.process_pending_file_reports"
        ),
        "generate_hashes": mocker.patch("mediator.mediator.generate_hashes"),
        "create_or_defer_file_report": mocker.patch(
            "mediator.mediator.create_or_defer_file_report"
        ),
        "create_task_report_in_db": mocker.patch(
            "mediator.mediator.create_task_report_in_db"
        ),
    }


def _run_process_successful_task(mocker, result_dict):
    celery_task = mocker.MagicMock()
    celery_task.uuid = "task-uuid"
    db_task = mocker.MagicMock()
    db_task.id = 42
    celery_app = mocker.MagicMock()

    mock_async_result = mocker.patch("mediator.mediator.AsyncResult")
    mock_async_result.return_value.get.return_value = _encode(result_dict)

    mediator.process_successful_task(mocker.MagicMock(), celery_task, db_task, celery_app)
    return db_task


def test_process_successful_task_creates_files_by_default(mocker, mediator_mocks):
    result_dict = _build_result(
        skip_file_creation=False,
        output_files=[{"uuid": "u1"}, {"uuid": "u2"}],
    )

    _run_process_successful_task(mocker, result_dict)

    # Two output files -> two DB rows + two hash jobs.
    assert mediator_mocks["create_file_in_database"].call_count == 2
    assert mediator_mocks["generate_hashes"].call_count == 2
    assert mediator_mocks["process_pending_file_reports"].call_count == 2


def test_process_successful_task_skips_output_file_db_creation(mocker, mediator_mocks):
    result_dict = _build_result(
        skip_file_creation=True,
        output_files=[{"uuid": "u1"}, {"uuid": "u2"}],
    )

    _run_process_successful_task(mocker, result_dict)

    mediator_mocks["create_file_in_database"].assert_not_called()
    mediator_mocks["generate_hashes"].assert_not_called()
    mediator_mocks["process_pending_file_reports"].assert_not_called()


def test_process_successful_task_still_creates_task_files_when_skipping(
    mocker, mediator_mocks
):
    """skip_file_creation must only affect output_files, not task_files/reports."""
    result_dict = _build_result(
        skip_file_creation=True,
        output_files=[{"uuid": "u1"}],
        task_files=[{"uuid": "log1"}],
    )

    db_task = _run_process_successful_task(mocker, result_dict)

    # output_files skipped, task_files still created (once).
    assert mediator_mocks["create_file_in_database"].call_count == 1
    # The one call was for the task (log) file, not the output file.
    task_file_args = mediator_mocks["create_file_in_database"].call_args_list[0]
    assert task_file_args.args[1] == {"uuid": "log1"}
    # Hashing still runs for the log file.
    assert mediator_mocks["generate_hashes"].call_count == 1


def test_process_successful_task_missing_flag_defaults_to_creating(
    mocker, mediator_mocks
):
    """Older workers may not set the key at all; default must be create-files."""
    result_dict = _build_result(output_files=[{"uuid": "u1"}])
    del result_dict["skip_file_creation"]

    _run_process_successful_task(mocker, result_dict)

    mediator_mocks["create_file_in_database"].assert_called_once()
    mediator_mocks["generate_hashes"].assert_called_once()
