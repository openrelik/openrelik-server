# Copyright 2024-2025 Google LLC
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

"""Tests for workflows endpoints."""

import json
from unittest.mock import ANY

import pytest
from celery.canvas import Signature
from fastapi import status
from sqlalchemy.orm import Session

from api.v1 import schemas
from datastores.sql.models.workflow import Workflow


@pytest.mark.asyncio
async def test_create_workflow(
    fastapi_async_test_client,
    mocker,
    folder_db_model,
    workflow_response,
    workflow_schema_mock,
):
    """Test create workflow route."""
    folder_id = 1
    mock_get_workflow_template_from_db = mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db"
    )
    mock_get_workflow_template_from_db.return_value = workflow_schema_mock
    mock_create_subfolder_in_db = mocker.patch("api.v1.workflows.create_subfolder_in_db")
    mock_create_subfolder_in_db.return_value = folder_db_model

    mock_create_workflow_in_db = mocker.patch("api.v1.workflows.create_workflow_in_db")
    mock_create_workflow_in_db.return_value = workflow_response

    request = {"template_id": 1, "folder_id": folder_id, "file_ids": [1, 2]}

    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/workflows/", json=request
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_workflow_no_template(
    fastapi_async_test_client, mocker, folder_db_model, workflow_response
):
    """Test create workflow route with no template."""

    mock_create_subfolder_in_db = mocker.patch("api.v1.workflows.create_subfolder_in_db")
    mock_create_subfolder_in_db.return_value = folder_db_model
    mock_create_workflow_in_db = mocker.patch("api.v1.workflows.create_workflow_in_db")
    mock_create_workflow_in_db.return_value = workflow_response

    folder_id = 1
    request = {"folder_id": folder_id, "file_ids": [1, 2]}

    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/workflows/", json=request
    )

    assert response.status_code == 200
    mock_create_subfolder_in_db.assert_called_once()


@pytest.mark.asyncio
async def test_create_workflow_no_template_no_files(
    fastapi_async_test_client, mocker, folder_db_model, workflow_response, workflow_schema_mock
):
    """Test create workflow route with no template and no files."""
    folder_id = 1
    mock_get_workflow_template_from_db = mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db"
    )
    mock_get_workflow_template_from_db.return_value = workflow_schema_mock
    mock_create_subfolder_in_db = mocker.patch("api.v1.workflows.create_subfolder_in_db")
    mock_create_subfolder_in_db.return_value = folder_db_model

    mock_create_workflow_in_db = mocker.patch("api.v1.workflows.create_workflow_in_db")
    mock_create_workflow_in_db.return_value = workflow_response
    folder_id = 1
    request = {"folder_id": folder_id}

    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/workflows/", json=request
    )
    assert response.status_code == 422  # invalid request, missing file_ids


def test_get_workflow(fastapi_test_client, mocker, workflow_response):
    """Test get workflow route."""
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_from_db")
    mock_get_workflow_from_db.return_value = workflow_response

    workflow_id = 1
    response = fastapi_test_client.get(f"/folders/1/workflows/{workflow_id}")
    assert response.status_code == 200
    assert response.json() == workflow_response.model_dump(mode="json")


@pytest.mark.asyncio
async def test_update_workflow(
    fastapi_async_test_client, mocker, workflow_db_model, workflow_response
):
    """Test update workflow route."""
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_from_db")
    mock_get_workflow_from_db.return_value = workflow_db_model

    mock_update_workflow_in_db = mocker.patch("api.v1.workflows.update_workflow_in_db")
    mock_update_workflow_in_db.return_value = workflow_response

    folder_id = 1
    workflow_id = 1
    updated_workflow_data = {
        "display_name": "updated workflow name",
        "spec_json": json.dumps({"tasks": []}),
    }

    response = await fastapi_async_test_client.patch(
        f"/folders/{folder_id}/workflows/{workflow_id}", json=updated_workflow_data
    )
    assert response.status_code == 200
    assert response.json() == workflow_response.model_dump(mode="json")


def test_get_workflows(fastapi_test_client, mocker, workflow_response):
    mock_get_folder_workflows_from_db = mocker.patch(
        "api.v1.workflows.get_folder_workflows_from_db"
    )
    mock_get_folder_workflows_from_db.return_value = [workflow_response]
    folder_id = 1

    response = fastapi_test_client.get(f"/folders/{folder_id}/workflows/workflows")
    assert response.status_code == 200
    assert response.json() == [workflow_response.model_dump(mode="json")]


@pytest.mark.asyncio
async def test_copy_workflow(
    fastapi_async_test_client, mocker, workflow_db_model, workflow_response
):
    """Test copy workflow route."""
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_from_db")
    mock_get_workflow_from_db.return_value = workflow_db_model

    mock_create_subfolder_in_db = mocker.patch("api.v1.workflows.create_subfolder_in_db")
    mock_create_subfolder_in_db.return_value = workflow_db_model.folder

    mock_create_workflow_in_db = mocker.patch("api.v1.workflows.create_workflow_in_db")
    mock_create_workflow_in_db.return_value = workflow_response

    folder_id = 1
    workflow_id = 1
    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/workflows/{workflow_id}/copy/"
    )

    assert response.status_code == 200


def test_delete_workflow(fastapi_test_client, mocker, db):
    mock_delete_workflow_from_db = mocker.patch("api.v1.workflows.delete_workflow_from_db")
    folder_id = 1
    workflow_id = 1

    response = fastapi_test_client.delete(f"/folders/{folder_id}/workflows/{workflow_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_delete_workflow_from_db.assert_called_once_with(db, workflow_id)


@pytest.mark.asyncio
async def test_run_workflow(
    fastapi_async_test_client,
    mocker,
    db: Session,
    workflow_db_model: Workflow,
    workflow_response: schemas.WorkflowResponse,
    file_db_model,
    setup_file_path_mock,
):
    """Test run workflow route."""
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_from_db")
    mock_get_workflow_from_db.return_value = workflow_db_model
    mock_create_workflow = mocker.patch("api.v1.workflows.create_workflow_signature")
    mock_create_workflow.return_value.apply_async.return_value = ANY
    mock_makedirs = mocker.patch("os.makedirs")
    mocker.patch("os.path.exists", return_value=False)  # Path doesn't exist

    folder_id = 1
    workflow_id = 1

    workflow_db_model.files = [file_db_model]
    request = {
        "workflow_spec": {
            "workflow": {
                "type": "chain",
                "tasks": [
                    {
                        "type": "task",
                        "task_name": "test_task",
                        "queue_name": "test_queue",
                        "task_config": [],
                        "tasks": [],
                        "uuid": "test_task_uuid",
                    }
                ],
            }
        }
    }
    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/workflows/{workflow_id}/run/",
        json=request,
    )

    assert response.status_code == 200

    # Check calls and parameters
    mock_get_workflow_from_db.assert_called_once_with(db, workflow_id)
    mock_makedirs.assert_called_once_with(workflow_db_model.folder.path)
    mock_create_workflow.assert_called_once()
    mock_create_workflow.return_value.apply_async.assert_called_once()


@pytest.mark.asyncio
async def test_run_workflow_nested_tasks(
    fastapi_async_test_client,
    mocker,
    db: Session,
    workflow_db_model: Workflow,
    workflow_response: schemas.WorkflowResponse,
    file_db_model,
    setup_file_path_mock,
):
    """Test run workflow route with group tasks."""
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_from_db")
    mock_get_workflow_from_db.return_value = workflow_db_model
    mock_create_workflow = mocker.patch("api.v1.workflows.create_workflow_signature")
    mock_create_workflow.return_value.apply_async.return_value = ANY
    mock_makedirs = mocker.patch("os.makedirs")
    mocker.patch("os.path.exists", return_value=False)  # Path doesn't exist

    folder_id = 1
    workflow_id = 1

    workflow_db_model.files = [file_db_model]

    nested_request = {
        "workflow_spec": {
            "workflow": {
                "type": "chain",
                "tasks": [
                    {
                        "type": "task",
                        "task_name": "task1",
                        "uuid": "task1_uuid",
                        "task_config": [],
                        "tasks": [
                            {
                                "type": "task",
                                "task_name": "task2",
                                "uuid": "task2_uuid",
                                "task_config": [],
                                "tasks": [],
                            }
                        ],
                    }
                ],
            }
        }
    }

    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/workflows/{workflow_id}/run/",
        json=nested_request,
    )

    assert response.status_code == 200

    # Check calls and parameters
    mock_get_workflow_from_db.assert_called_once_with(db, workflow_id)
    mock_makedirs.assert_called_once_with(workflow_db_model.folder.path)
    mock_create_workflow.assert_called_once()
    mock_create_workflow.return_value.apply_async.assert_called_once()


@pytest.mark.asyncio
async def test_get_workflow_templates(
    fastapi_async_test_client, mocker, workflow_template_response
):
    """Test get workflow templates route."""
    mock_get_workflow_templates_from_db = mocker.patch(
        "api.v1.workflows.get_workflow_templates_from_db"
    )
    mock_get_workflow_templates_from_db.return_value = [workflow_template_response]

    response = await fastapi_async_test_client.get("/workflows/templates/")
    assert response.status_code == 200
    assert response.json() == [workflow_template_response.model_dump(mode="json")]


@pytest.mark.asyncio
async def test_get_workflow_template_by_id(
    fastapi_async_test_client, mocker, workflow_template_response
):
    """Test get workflow template by id route."""
    mock_get_workflow_template_by_id = mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db"
    )
    mock_get_workflow_template_by_id.return_value = workflow_template_response

    workflow_template_id = 1
    response = await fastapi_async_test_client.get(f"/workflows/templates/{workflow_template_id}")
    assert response.status_code == 200
    assert response.json() == workflow_template_response.model_dump(mode="json")


@pytest.mark.asyncio
async def test_create_workflow_template(
    fastapi_async_test_client,
    mocker,
    workflow_db_model,
    workflow_template_response,
):
    """Test create workflow template route."""
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_from_db")
    mock_get_workflow_from_db.return_value = workflow_db_model
    mock_create_workflow_template_in_db = mocker.patch(
        "api.v1.workflows.create_workflow_template_in_db"
    )
    mock_create_workflow_template_in_db.return_value = workflow_template_response

    request = {"display_name": "test template", "workflow_id": 1}
    response = await fastapi_async_test_client.post("/workflows/templates/", json=request)
    assert response.status_code == 200

    # Verify that the spec_json is stringified before being passed to the database function
    kwargs = mock_create_workflow_template_in_db.call_args_list[0]
    created_template = kwargs[0][1]
    assert isinstance(created_template.spec_json, str)


@pytest.mark.asyncio
async def test_update_workflow_template(
    fastapi_async_test_client, mocker, template_db_model, workflow_template_response
):
    """Test update workflow route."""
    mock_get_workflow_template_from_db = mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db"
    )
    mock_get_workflow_template_from_db.return_value = template_db_model

    mock_update_workflow_template_in_db = mocker.patch(
        "api.v1.workflows.update_workflow_template_in_db"
    )
    mock_update_workflow_template_in_db.return_value = template_db_model

    template_id = 1
    updated_workflow_template_data = {
        "id": 1,
        "created_at": "2025-06-25T14:03:51.095829Z",
        "updated_at": "2025-06-25T14:03:51.095829Z",
        "deleted_at": None,
        "is_deleted": False,
        "display_name": "strings",
        "description": None,
        "spec_json": json.dumps(
            {
                "workflow": {
                    "type": "chain",
                    "tasks": [
                        {
                            "type": "task",
                            "task_name": "task_1",
                            "queue_name": "default",
                            "task_config": {"arg_1": "value_1", "arg_2": 2},
                            "tasks": [],
                        },
                        {
                            "type": "task",
                            "task_name": "task_2",
                            "queue_name": "default",
                            "task_config": {},
                            "tasks": [],
                        },
                    ],
                }
            }
        ),
        "user_id": 1,
    }

    response = await fastapi_async_test_client.patch(
        f"/workflows/templates/{template_id}", json=updated_workflow_template_data
    )
    assert response.status_code == 200
    assert response.json() == workflow_template_response.model_dump(mode="json")


@pytest.mark.asyncio
async def test_create_workflow_template_invalid_workflow(fastapi_async_test_client, mocker, db):
    """Test create workflow template route with invalid workflow ID."""

    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_from_db")
    mock_get_workflow_from_db.return_value = None  # Simulate not finding workflow.

    request = {"display_name": "test template", "workflow_id": 1}

    response = await fastapi_async_test_client.post("/workflows/templates/", json=request)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_create_workflow_signature_invalid_type(
    mocker, db: Session, regular_user: schemas.User, workflow_schema_mock
):
    """Test create_workflow_signature function with an invalid task type."""
    task_data = {"type": "invalid_type"}
    input_files = []
    output_path = ""
    with pytest.raises(ValueError):
        from api.v1.workflows import create_workflow_signature

        create_workflow_signature(
            db, regular_user, task_data, input_files, output_path, workflow_schema_mock
        )


def test_replace_uuids_dict(mocker):
    data = {"uuid": "old_uuid", "nested": {"uuid": "nested_old_uuid"}}
    from api.v1.workflows import replace_uuids

    replace_uuids(data)

    assert data["uuid"] != "old_uuid"
    assert data["nested"]["uuid"] != "nested_old_uuid"
    assert isinstance(data["uuid"], str)
    assert isinstance(data["nested"]["uuid"], str)


def test_replace_uuids_list(mocker):
    data = [{"uuid": "old_uuid"}, {"uuid": "another_old_uuid"}]
    from api.v1.workflows import replace_uuids

    replace_uuids(data)
    assert data[0]["uuid"] != "old_uuid"
    assert data[1]["uuid"] != "another_old_uuid"

    assert isinstance(data[0]["uuid"], str)
    assert isinstance(data[1]["uuid"], str)


def test_replace_uuids_replace_with(mocker):
    data = {"uuid": "old_uuid"}
    replace_value = "new_uuid"

    from api.v1.workflows import replace_uuids

    replace_uuids(data, replace_with=replace_value)
    assert data["uuid"] == replace_value


def test_get_task_signature(mocker, db, user_db_model, task_response, workflow_db_model):
    """Test get_task_signature function."""

    mock_create_task_in_db = mocker.patch("api.v1.workflows.create_task_in_db")
    mock_create_task_in_db.return_value = task_response
    task_data = {
        "task_name": "test_task",
        "queue_name": "test_queue",
        "task_config": [{"name": "param1", "value": "value1"}],
        "uuid": "test_uuid",
    }
    input_files = []
    output_path = "/tmp/output"

    from api.v1.workflows import get_task_signature

    task_signature = get_task_signature(
        db, user_db_model, task_data, input_files, output_path, workflow_db_model
    )

    assert isinstance(task_signature, Signature)
    mock_create_task_in_db.assert_called_once()
    created_task = mock_create_task_in_db.call_args[0][1]
    assert created_task.display_name is None
    assert created_task.description is None
    assert created_task.uuid == "test_uuid"
    assert json.loads(created_task.config) == {"param1": "value1"}
