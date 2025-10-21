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

from unittest.mock import MagicMock

import pytest

from lib.reporting_utils import Priority, create_workflow_report


@pytest.fixture
def mock_config(monkeypatch):
    """Fixture to mock the config module."""
    mock_config_dict = {"server": {"ui_server_url": "https://example.com"}}
    monkeypatch.setattr(
        "lib.reporting_utils.config", MagicMock(get=lambda *args: mock_config_dict.get(*args))
    )


@pytest.fixture
def mock_workflow():
    """Fixture to create a mock workflow object with a task and a report."""
    # Mock workflow and folder
    mock_folder = MagicMock(id="123")
    mock_workflow = MagicMock(display_name="Test Workflow", folder=mock_folder, tasks=[])

    # Mock task and reports
    mock_task = MagicMock(
        display_name="Test Task",
        runtime=10.5123,
        task_report=MagicMock(
            priority=Priority.HIGH,
            summary="High Priority Summary",
            markdown="This is a test report.",
        ),
        file_reports=[],
    )

    # Mock file report
    mock_source_file = MagicMock(
        display_name="source_file.txt",
        folder=mock_folder,
        id="source_file_id_456",
    )
    mock_file = MagicMock(
        display_name="test_file.txt",
        original_path="path/to/original/file.txt",
        source_file=mock_source_file,
        id="file_id_789",
    )

    mock_file_report = MagicMock(
        priority=Priority.CRITICAL,
        summary="Critical File Report",
        markdown="This is a critical file report.",
        file=mock_file,
    )

    mock_task.file_reports = [mock_file_report]
    mock_workflow.tasks = [mock_task]

    return mock_workflow


def test_create_workflow_report(mock_workflow, mock_config):
    """Test that create_workflow_report generates the correct markdown string."""
    # Call the function with the mock workflow object
    report_output = create_workflow_report(mock_workflow)

    # Define the expected output string
    expected_output = (
        "# OpenRelik: Test Workflow\n"
        "## Test Workflow\n"
        "https://example.com/folder/123/\n"
        "## **High Priority Summary**\n"
        "* Task: Test Task (10.51s)\n"
        "* Priority: HIGH\n"
        "##### Details\n"
        "This is a test report.\n"
        "---\n\n"
        "## **Critical File Report**\n"
        "* Task: Test Task (10.51s)\n"
        "* Priority: CRITICAL\n"
        "* Link to artifact: [test_file.txt](https://example.com/folder/123/file/file_id_789)\n"
        "* Extracted from: [source_file.txt](https://example.com/folder/123/file/source_file_id_456)\n"
        "* Original path: path/to/original/file.txt\n"
        "##### Details\n"
        "This is a critical file report.\n"
        "---"
    )

    # Assert that the generated report matches the expected output
    assert report_output.strip() == expected_output.strip()
