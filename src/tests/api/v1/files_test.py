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

"""Tests for files endpoints."""

import json
import os
import pytest
from fastapi import UploadFile
from pathlib import Path


@pytest.mark.parametrize(
    "theme, expected_background, expected_color",
    [("light", "#fff", "#000"), ("dark", "#000", "#fff")],
)
def test_get_file_content(
    fastapi_test_client,
    mocker,
    file_db_model,
    theme,
    expected_background,
    expected_color,
):
    """Test the get_file_content endpoint."""
    mock_get_file_from_db = mocker.patch("api.v1.files.get_file_from_db")
    mock_get_file_from_db.return_value = file_db_model
    mock_config = mocker.patch("datastores.sql.models.folder.get_config")
    file_content = "Mocked file content"
    mock_open = mocker.mock_open(read_data=file_content)
    mocker.patch("builtins.open", mock_open)
    response = fastapi_test_client.get(
        f"/files/{file_db_model.id}/content?theme={theme}"
    )
    assert response.status_code == 200
    assert f'<html style="background:{expected_background}">' in response.text
    assert (
        f'<pre style="color:{expected_color};padding:10px;white-space: pre-wrap;">{file_content}</pre>'
        in response.text
    )
    mock_open.assert_called_with(file_db_model.path, "r", encoding="utf-8")


def test_get_file_content_file_not_found(
    fastapi_test_client, mocker, file_db_model, tmp_path
):
    """Test the get_file_content endpoint when file not found."""
    non_existent_path = os.path.join(tmp_path, "does_not_exist.txt")
    file_db_model.original_path = (
        non_existent_path  #  Set the path to a non-existent file
    )
    mock_get_file_from_db = mocker.patch("api.v1.files.get_file_from_db")
    mock_get_file_from_db.return_value = file_db_model
    response = fastapi_test_client.get(f"/files/{file_db_model.id}/content")
    assert response.status_code == 200
    assert (
        '<pre style="color:#000;padding:10px;white-space: pre-wrap;">File not found</pre>'
        in response.text
    )


@pytest.mark.parametrize(
    "file_id, display_name", [(1, "file1.txt"), (2, "another_file.pdf")]
)
def test_download_file(fastapi_test_client, mocker, file_id, display_name, tmp_path):
    mock_file_response = mocker.Mock()
    mock_file_response.id = file_id
    mock_file_response.display_name = display_name
    mock_file_response.path = os.path.join(tmp_path, display_name)

    with open(mock_file_response.path, "w") as f:
        f.write("Dummy file content")

    mock_get_file_from_db = mocker.patch("api.v1.files.get_file_from_db")
    mock_get_file_from_db.return_value = mock_file_response
    response = fastapi_test_client.get(f"/files/{file_id}/download")
    assert response.status_code == 200
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{display_name}"'
    )


@pytest.mark.asyncio
async def test_upload_files(
    fastapi_async_test_client, mocker, folder_db_model, file_db_model, file_response
):
    """Test the upload_files endpoint."""
    mock_config = mocker.patch("datastores.sql.models.folder.get_config")
    storage_path = Path(file_db_model.original_path).parent.parent
    mock_config.return_value = {"server": {"storage_path": storage_path}}

    mock_get_folder_from_db = mocker.patch("api.v1.files.get_folder_from_db")
    mock_get_folder_from_db.return_value = folder_db_model
    mock_create_file_in_db = mocker.patch("api.v1.files.create_file_in_db")
    mock_create_file_in_db.return_value = file_response
    mock_background_tasks_add_task = mocker.patch(
        "api.v1.files.BackgroundTasks.add_task"
    )

    resumable_identifier = "12345"
    resumable_filename = "test_file.txt"
    folder_id = folder_db_model.id

    def mock_file_read(size):
        return b"test file content"

    mock_file = mocker.MagicMock(spec=UploadFile)
    mock_file.read = mock_file_read
    response = await fastapi_async_test_client.post(
        "/files/upload",
        files={"file": ("test_file.txt", b"test file content")},
        params={
            "resumableChunkNumber": 1,
            "resumableChunkSize": 1024,
            "resumableCurrentChunkSize": len(b"test file content"),
            "resumableTotalSize": len(b"test file content"),
            "resumableTotalChunks": 1,
            "resumableIdentifier": resumable_identifier,
            "resumableFilename": resumable_filename,
            "folder_id": folder_id,
        },
    )
    assert response.status_code == 201
    assert response.json() == file_response.model_dump()



def test_get_workflows_empty(fastapi_test_client, mocker):
    """Test the get_workflows endpoint."""
    mock_get_file_workflows_from_db = mocker.patch(
        "api.v1.files.get_file_workflows_from_db"
    )
    mock_get_file_workflows_from_db.return_value = []
    file_id = 1

    response = fastapi_test_client.get(f"/files/{file_id}/workflows")
    assert response.status_code == 200


def test_get_workflows(fastapi_test_client, mocker, workflow_response):
    """Test the get_workflows endpoint."""
    mock_get_file_workflows_from_db = mocker.patch(
        "api.v1.files.get_file_workflows_from_db"
    )
    mock_get_file_workflows_from_db.return_value = [workflow_response]
    file_id = 1

    response = fastapi_test_client.get(f"/files/{file_id}/workflows")
    assert response.status_code == 200


def test_generate_file_summary(
    fastapi_test_client,
    mocker,
    file_db_model,
):
    """Test generate_file_summary endpoint."""
    mock_get_active_llms = mocker.patch("api.v1.files.get_active_llms")
    mock_get_active_llms.return_value = [
        {"name": "test_llm", "config": {"model": "test_model"}}
    ]
    mock_create_file_summary_in_db = mocker.patch(
        "api.v1.files.create_file_summary_in_db"
    )
    mock_background_tasks_add_task = mocker.patch(
        "api.v1.files.BackgroundTasks.add_task"
    )

    response = fastapi_test_client.post(f"/files/{file_db_model.id}/summaries")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_download_file_stream(fastapi_async_test_client, mocker, file_db_model):
    """Test the download_file_stream endpoint."""
    mock_config = mocker.patch("datastores.sql.models.folder.get_config")
    storage_path = Path(file_db_model.original_path).parent.parent
    mock_config.return_value = {"server": {"storage_path": storage_path}}
    mock_get_file_from_db = mocker.patch("api.v1.files.get_file_from_db")
    mock_get_file_from_db.return_value = file_db_model

    with open(file_db_model.path, "w") as f:
        f.write("Dummy file content")

    response = await fastapi_async_test_client.get(
        f"/files/{file_db_model.id}/download_stream"
    )
    assert response.status_code == 200
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{file_db_model.display_name}"'
    )

    streamed_content = b""
    for chunk in response.iter_bytes():
        streamed_content += chunk
    assert streamed_content == b"Dummy file content"


@pytest.mark.asyncio
async def test_upload_files_chunked(
    fastapi_async_test_client, mocker, folder_db_model, file_db_model, file_response
):
    """Test upload_files endpoint with chunked uploads."""
    mock_config = mocker.patch("datastores.sql.models.folder.get_config")
    storage_path = Path(file_db_model.original_path).parent.parent
    mock_config.return_value = {"server": {"storage_path": storage_path}}
    mock_get_folder_from_db = mocker.patch("api.v1.files.get_folder_from_db")
    mock_get_folder_from_db.return_value = folder_db_model
    mock_create_file_in_db = mocker.patch("api.v1.files.create_file_in_db")
    mock_create_file_in_db.return_value = file_response
    mock_background_tasks_add_task = mocker.patch(
        "api.v1.files.BackgroundTasks.add_task"
    )
    resumable_identifier = "12345"
    resumable_filename = "test_file.txt"
    folder_id = folder_db_model.id
    chunk_size = 1024
    total_chunks = 3
    total_size = chunk_size * total_chunks
    chunk_number = 1
    current_chunk_size = (
        chunk_size if chunk_number < total_chunks else total_size % chunk_size
    )

    chunk_content = b"test file content" * (chunk_size // len(b"test file content"))
    response = await fastapi_async_test_client.post(
        "/files/upload",
        files={"file": ("test_file.txt", chunk_content)},
        params={
            "resumableChunkNumber": chunk_number,
            "resumableChunkSize": chunk_size,
            "resumableCurrentChunkSize": (
                current_chunk_size if chunk_number == total_chunks else chunk_size
            ),
            "resumableTotalSize": total_size,
            "resumableTotalChunks": total_chunks,
            "resumableIdentifier": resumable_identifier,
            "resumableFilename": resumable_filename,
            "folder_id": folder_id,
        },
    )
    assert response.status_code == 201


def test_get_task(fastapi_test_client, mocker, db, task_response):
    """Test the get_task endpoint."""
    mock_get_task_from_db = mocker.patch("api.v1.files.get_task_from_db")
    mock_get_task_from_db.return_value = [task_response]

    file_id = 1
    workflow_id = 1
    task_id = 1
    response = fastapi_test_client.get(
        f"/files/{file_id}/workflows/{workflow_id}/tasks/{task_id}"
    )

    assert response.status_code == 200
    mock_get_task_from_db.assert_called_once_with(db, task_id)

    assert response.json() == [task_response.model_dump(mode="json")]


def test_get_file_summary(fastapi_test_client, mocker, db):
    """Test the get_file_summary endpoint."""

    mock_summary = {
        "id": 1,
        "summary": "test summary",
        "status_short": None,
        "status_detail": None,
        "status_progress": None,
        "runtime": 0.0,
        "llm_model_prompt": None,
        "llm_model_provider": None,
        "llm_model_name": None,
        "llm_model_config": None,
        "file_id": 1,
    }
    mock_get_file_summary_from_db = mocker.patch(
        "api.v1.files.get_file_summary_from_db"
    )
    mock_get_file_summary_from_db.return_value = mock_summary

    file_id = 1
    summary_id = 1

    response = fastapi_test_client.get(f"/files/{file_id}/summaries/{summary_id}")
    assert response.status_code == 200
    assert response.json() == mock_summary


def test_download_task_result(fastapi_test_client, mocker, db, tmp_path):
    """Test the download_task_result endpoint."""
    file_id = 1
    workflow_id = 1
    task_id = 1

    result_file_path = os.path.join(tmp_path, "test_result.txt")
    with open(result_file_path, "w") as f:
        f.write("Test result content")

    mock_task = mocker.Mock()
    mock_task.result = json.dumps({"output_file_path": result_file_path})
    db.get.return_value = mock_task

    response = fastapi_test_client.post(
        f"/files/{file_id}/workflows/{workflow_id}/tasks/{task_id}/download"
    )

    assert response.status_code == 200
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="test_result.txt"'
    )
    assert response.content == b"Test result content"
