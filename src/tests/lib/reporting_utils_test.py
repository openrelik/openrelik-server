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

from lib.reporting_utils import create_workflow_report, Priority

@pytest.fixture
def mock_reporting_config(mocker):
    """Fixture to provide a mock config for reporting_utils."""
    mock_config = mocker.patch("lib.reporting_utils.config")
    mock_config.get.return_value = {"ui_server_url": "http://localhost"}
    return mock_config

def test_create_workflow_report(mocker, mock_reporting_config):
    """Test create_workflow_report with a complete workflow."""
    # Mock workflow hierarchy
    mock_workflow = mocker.MagicMock()
    mock_workflow.display_name = "Test Workflow"
    mock_workflow.folder.id = 1
    
    mock_task = mocker.MagicMock()
    mock_task.display_name = "Test Task"
    mock_task.runtime = 10.5
    
    mock_task_report = mocker.MagicMock()
    mock_task_report.priority = Priority.HIGH
    mock_task_report.summary = "Task Summary"
    mock_task_report.markdown = "Task Markdown"
    mock_task.task_report = mock_task_report
    
    # Mock file report
    mock_file_report = mocker.MagicMock()
    mock_file_report.priority = Priority.CRITICAL
    mock_file_report.summary = "File Summary"
    mock_file_report.markdown = "File Markdown"
    
    mock_file = mocker.MagicMock()
    mock_file.id = 2
    mock_file.display_name = "test.txt"
    mock_file.original_path = "/path/to/test.txt"
    mock_file.hash_sha1 = "sha1"
    mock_file.source_file = None
    
    mock_file_report.file = mock_file
    mock_task.file_reports = [mock_file_report]
    
    mock_workflow.tasks = [mock_task]
    
    report = create_workflow_report(mock_workflow)
    
    assert "OpenRelik: Test Workflow" in report
    assert "Task Summary" in report
    assert "Task Markdown" in report
    assert "File Summary" in report
    assert "File Markdown" in report
    assert "Link to artifact: [test.txt]" in report

def test_create_workflow_report_no_reports(mocker, mock_reporting_config):
    """Test create_workflow_report when no reports match criteria."""
    mock_workflow = mocker.MagicMock()
    mock_workflow.display_name = "Test Workflow"
    mock_workflow.folder.id = 1
    
    mock_task = mocker.MagicMock()
    mock_task.task_report = None
    mock_task.file_reports = []
    mock_workflow.tasks = [mock_task]
    
    report = create_workflow_report(mock_workflow, min_priority=Priority.CRITICAL)
    
    assert "No reports matching the priority filter were found" in report

def test_create_workflow_report_with_source_file(mocker, mock_reporting_config):
    """Test create_workflow_report for a file with a source file."""
    mock_workflow = mocker.MagicMock()
    mock_workflow.display_name = "Test Workflow"
    mock_workflow.folder.id = 1
    
    mock_task = mocker.MagicMock()
    mock_task.display_name = "Test Task"
    mock_task.runtime = 1.0
    mock_task.task_report = None
    
    mock_file_report = mocker.MagicMock()
    mock_file_report.priority = Priority.MEDIUM
    mock_file_report.summary = "File Summary"
    mock_file_report.markdown = "File Markdown"
    
    mock_file = mocker.MagicMock()
    mock_file.id = 2
    mock_file.display_name = "extracted.txt"
    mock_file.original_path = None
    mock_file.hash_sha1 = "sha1"
    
    mock_source_file = mocker.MagicMock()
    mock_source_file.id = 3
    mock_source_file.display_name = "original.zip"
    mock_source_file.folder.id = 1
    mock_file.source_file = mock_source_file
    
    mock_file_report.file = mock_file
    mock_task.file_reports = [mock_file_report]
    mock_workflow.tasks = [mock_task]
    
    # Set min_priority low enough to include MEDIUM
    report = create_workflow_report(mock_workflow, min_priority=Priority.LOW)
    
    assert "Extracted from: [original.zip]" in report

def test_create_workflow_report_duplicate_filtering(mocker, mock_reporting_config):
    """Test that duplicate file reports are filtered out."""
    mock_workflow = mocker.MagicMock()
    mock_workflow.display_name = "Test Workflow"
    mock_workflow.folder.id = 1
    
    mock_task = mocker.MagicMock()
    mock_task.display_name = "Test Task"
    mock_task.runtime = 1.0
    mock_task.task_report = None
    
    def create_mock_file_report():
        fr = mocker.MagicMock()
        fr.priority = Priority.HIGH
        fr.summary = "Summary"
        fr.markdown = "Markdown"
        fr.file.id = 2
        fr.file.display_name = "file.txt"
        fr.file.original_path = "/path"
        fr.file.hash_sha1 = "sha1"
        fr.file.source_file = None
        return fr
        
    fr1 = create_mock_file_report()
    fr2 = create_mock_file_report() # Duplicate
    
    mock_task.file_reports = [fr1, fr2]
    mock_workflow.tasks = [mock_task]
    
    report = create_workflow_report(mock_workflow)
    
    # Count occurrences of "Summary"
    assert report.count("Summary") == 1
