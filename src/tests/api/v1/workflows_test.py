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

import pytest
from celery.canvas import Signature
from fastapi import status
from sqlalchemy.orm import Session

from api.v1 import schemas
from datastores.sql.models.folder import Folder
from datastores.sql.models.role import Role
from datastores.sql.models.workflow import Workflow

from lib.workflow_utils import get_task_signature


def _allow_file_access(mocker, is_deleted=False, has_access=True):
    """Mock the file lookups that create_workflow does for its file_ids."""
    mock_file = mocker.MagicMock(is_deleted=is_deleted)
    mocker.patch("api.v1.workflows.get_file_from_db", return_value=mock_file)
    return mocker.patch("api.v1.workflows.check_user_access", return_value=has_access)


@pytest.mark.asyncio
async def test_create_workflow(
    fastapi_async_test_client,
    mocker,
    folder_db_model,
    workflow_response,
    workflow_schema_mock,
):
    """Test create workflow route."""
    _allow_file_access(mocker)
    folder_id = 1
    mock_get_workflow_template_from_db = mocker.patch(
        "lib.workflow_utils.get_workflow_template_from_db"
    )
    mock_get_workflow_template_from_db.return_value = workflow_schema_mock
    mock_create_subfolder_in_db = mocker.patch(
        "lib.workflow_utils.create_subfolder_in_db"
    )
    mock_create_subfolder_in_db.return_value = folder_db_model

    mock_create_workflow_in_db = mocker.patch(
        "lib.workflow_utils.create_workflow_in_db"
    )
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
    _allow_file_access(mocker)

    mock_create_subfolder_in_db = mocker.patch(
        "lib.workflow_utils.create_subfolder_in_db"
    )
    mock_create_subfolder_in_db.return_value = folder_db_model
    mock_create_workflow_in_db = mocker.patch(
        "lib.workflow_utils.create_workflow_in_db"
    )
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
    fastapi_async_test_client,
    mocker,
    folder_db_model,
    workflow_response,
    workflow_schema_mock,
):
    """Test create workflow route with no template and no files."""
    folder_id = 1
    mock_get_workflow_template_from_db = mocker.patch(
        "lib.workflow_utils.get_workflow_template_from_db"
    )
    mock_get_workflow_template_from_db.return_value = workflow_schema_mock
    mock_create_subfolder_in_db = mocker.patch(
        "lib.workflow_utils.create_subfolder_in_db"
    )
    mock_create_subfolder_in_db.return_value = folder_db_model

    mock_create_workflow_in_db = mocker.patch(
        "lib.workflow_utils.create_workflow_in_db"
    )
    mock_create_workflow_in_db.return_value = workflow_response
    folder_id = 1
    request = {"folder_id": folder_id}

    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/workflows/", json=request
    )
    assert response.status_code == 422  # invalid request, missing file_ids


def test_get_workflow(fastapi_test_client, mocker, workflow_response):
    """Test get workflow route."""
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_with_access")
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
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_with_access")
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
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_with_access")
    mock_get_workflow_from_db.return_value = workflow_db_model
    parent_folder = Folder(id=10)
    workflow_db_model.folder.parent = parent_folder
    mocker.patch("api.v1.workflows.check_user_access", return_value=True)

    mock_create_subfolder_in_db = mocker.patch(
        "api.v1.workflows.create_subfolder_in_db"
    )
    mock_create_subfolder_in_db.return_value = workflow_db_model.folder

    mock_create_workflow_in_db = mocker.patch("api.v1.workflows.create_workflow_in_db")
    mock_create_workflow_in_db.return_value = workflow_response

    folder_id = 1
    workflow_id = 1
    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/workflows/{workflow_id}/copy/"
    )

    assert response.status_code == 200
    assert mock_create_subfolder_in_db.call_args.kwargs["folder_id"] == parent_folder.id


def test_delete_workflow(fastapi_test_client, mocker, db):
    mock_delete_workflow_from_db = mocker.patch(
        "api.v1.workflows.delete_workflow_from_db"
    )
    folder_id = 1
    workflow_id = 1

    response = fastapi_test_client.delete(
        f"/folders/{folder_id}/workflows/{workflow_id}"
    )

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
    mocker.patch("api.v1.workflows.check_user_access", return_value=True)
    mocker.patch(
        "datastores.sql.models.folder.get_config",
        return_value={"server": {"storage_path": "/tmp/test"}},
    )
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_with_access")
    mock_get_workflow_from_db.return_value = workflow_db_model
    mock_create_workflow = mocker.patch("lib.workflow_utils.create_workflow_signature")
    mock_create_workflow.return_value.apply_async.return_value = mocker.ANY
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
    mock_get_workflow_from_db.assert_called_once_with(
        db, mocker.ANY, workflow_id, [Role.EDITOR, Role.OWNER]
    )
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
    mocker.patch("api.v1.workflows.check_user_access", return_value=True)
    mocker.patch(
        "datastores.sql.models.folder.get_config",
        return_value={"server": {"storage_path": "/tmp/test"}},
    )
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_with_access")
    mock_get_workflow_from_db.return_value = workflow_db_model
    mock_create_workflow = mocker.patch("lib.workflow_utils.create_workflow_signature")
    mock_create_workflow.return_value.apply_async.return_value = mocker.ANY
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
    mock_get_workflow_from_db.assert_called_once_with(
        db, mocker.ANY, workflow_id, [Role.EDITOR, Role.OWNER]
    )
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
    response = await fastapi_async_test_client.get(
        f"/workflows/templates/{workflow_template_id}"
    )
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
    mock_get_workflow_from_db = mocker.patch("api.v1.workflows.get_workflow_with_access")
    mock_get_workflow_from_db.return_value = workflow_db_model
    mock_create_workflow_template_in_db = mocker.patch(
        "api.v1.workflows.create_workflow_template_in_db"
    )
    mock_create_workflow_template_in_db.return_value = workflow_template_response

    request = {"display_name": "test template", "workflow_id": 1}
    response = await fastapi_async_test_client.post(
        "/workflows/templates/", json=request
    )
    assert response.status_code == 200

    # Verify that the spec_json is stringified before being passed to the database function
    kwargs = mock_create_workflow_template_in_db.call_args_list[0]
    created_template = kwargs[0][1]
    assert isinstance(created_template.spec_json, str)


@pytest.mark.asyncio
async def test_update_workflow_template(
    fastapi_async_test_client,
    mocker,
    template_db_model,
    workflow_template_response,
    user_response,
):
    """Test update workflow route."""
    template_db_model.user_id = user_response.id
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
    expected = workflow_template_response.model_copy(
        update={"user_id": user_response.id}
    )
    assert response.json() == expected.model_dump(mode="json")

    # Only the name and description are updated, on the template in the path.
    update = mock_update_workflow_template_in_db.call_args[0][1]
    assert update.id == template_id
    assert update.display_name == "strings"
    assert "spec_json" not in update.model_dump()


@pytest.mark.asyncio
async def test_update_workflow_template_not_creator(
    fastapi_async_test_client, mocker, template_db_model, user_response
):
    """Any user can rename a template, not only its creator."""
    template_db_model.user_id = user_response.id + 1
    mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db",
        return_value=template_db_model,
    )
    mock_update = mocker.patch("api.v1.workflows.update_workflow_template_in_db")
    mock_update.return_value = template_db_model

    response = await fastapi_async_test_client.patch(
        "/workflows/templates/1", json={"display_name": "renamed"}
    )
    assert response.status_code == status.HTTP_200_OK
    mock_update.assert_called_once()


@pytest.mark.asyncio
async def test_update_workflow_template_not_found(fastapi_async_test_client, mocker):
    """Updating a template that does not exist is a 404."""
    mocker.patch("api.v1.workflows.get_workflow_template_from_db", return_value=None)

    response = await fastapi_async_test_client.patch(
        "/workflows/templates/1", json={"display_name": "renamed"}
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
@pytest.mark.parametrize("display_name", ["", "   ", None])
async def test_update_workflow_template_empty_display_name(
    fastapi_async_test_client, mocker, template_db_model, display_name
):
    """An empty display name is rejected instead of silently ignored."""
    mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db",
        return_value=template_db_model,
    )
    mock_update = mocker.patch("api.v1.workflows.update_workflow_template_in_db")

    response = await fastapi_async_test_client.patch(
        "/workflows/templates/1", json={"display_name": display_name}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_update_workflow_template_clear_description(
    fastapi_async_test_client, mocker, template_db_model
):
    """Sending a null description passes it through so it gets cleared."""
    mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db",
        return_value=template_db_model,
    )
    mock_update = mocker.patch("api.v1.workflows.update_workflow_template_in_db")
    mock_update.return_value = template_db_model

    response = await fastapi_async_test_client.patch(
        "/workflows/templates/1", json={"description": None}
    )
    assert response.status_code == status.HTTP_200_OK
    update = mock_update.call_args[0][1]
    assert update.model_dump(exclude_unset=True) == {"id": 1, "description": None}


@pytest.mark.asyncio
async def test_update_workflow_template_includes_creator(
    fastapi_async_test_client, mocker, template_db_model, user_db_model
):
    """The response names the template's creator."""
    template_db_model.user_id = user_db_model.id
    template_db_model.user = user_db_model
    mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db",
        return_value=template_db_model,
    )
    mock_update = mocker.patch("api.v1.workflows.update_workflow_template_in_db")
    mock_update.return_value = template_db_model

    response = await fastapi_async_test_client.patch(
        "/workflows/templates/1", json={"display_name": "renamed"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["user"] == {
        "id": user_db_model.id,
        "display_name": "test_user",
        "username": "test_user",
        "profile_picture_url": "http://localhost/profile/pic",
        "uuid": user_db_model.uuid.hex,
    }


@pytest.mark.asyncio
async def test_update_orphaned_workflow_template(
    fastapi_async_test_client, mocker, template_db_model
):
    """A template without a creator still serializes in the response."""
    template_db_model.user_id = None
    mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db",
        return_value=template_db_model,
    )
    mock_update = mocker.patch("api.v1.workflows.update_workflow_template_in_db")
    mock_update.return_value = template_db_model

    response = await fastapi_async_test_client.patch(
        "/workflows/templates/1", json={"display_name": "renamed"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["user_id"] is None
    assert response.json()["user"] is None


@pytest.mark.asyncio
async def test_delete_workflow_template(
    fastapi_async_test_client, mocker, template_db_model, user_response
):
    """The creator of a template can delete it."""
    template_db_model.user_id = user_response.id
    mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db",
        return_value=template_db_model,
    )
    mock_delete = mocker.patch("api.v1.workflows.delete_workflow_template_from_db")

    response = await fastapi_async_test_client.delete("/workflows/templates/1")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == 1


@pytest.mark.asyncio
async def test_delete_workflow_template_not_creator(
    fastapi_async_test_client, mocker, template_db_model, user_response
):
    """Only the creator of a template can delete it."""
    template_db_model.user_id = user_response.id + 1
    mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db",
        return_value=template_db_model,
    )
    mock_delete = mocker.patch("api.v1.workflows.delete_workflow_template_from_db")

    response = await fastapi_async_test_client.delete("/workflows/templates/1")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_workflow_template_not_found(fastapi_async_test_client, mocker):
    """Deleting a template that does not exist is a 404."""
    mocker.patch("api.v1.workflows.get_workflow_template_from_db", return_value=None)
    mock_delete = mocker.patch("api.v1.workflows.delete_workflow_template_from_db")

    response = await fastapi_async_test_client.delete("/workflows/templates/1")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    mock_delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_offset", [1, None])
async def test_delete_workflow_template_as_admin(
    fastapi_async_test_client, mocker, template_db_model, user_response, owner_offset
):
    """Admins can delete templates owned by other users and orphaned templates."""
    template_db_model.user_id = (
        None if owner_offset is None else user_response.id + owner_offset
    )
    mocker.patch.object(user_response, "is_admin", True)
    mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db",
        return_value=template_db_model,
    )
    mock_delete = mocker.patch("api.v1.workflows.delete_workflow_template_from_db")

    response = await fastapi_async_test_client.delete("/workflows/templates/1")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_orphaned_workflow_template_not_admin(
    fastapi_async_test_client, mocker, template_db_model
):
    """Non-admins cannot delete orphaned templates."""
    template_db_model.user_id = None
    mocker.patch(
        "api.v1.workflows.get_workflow_template_from_db",
        return_value=template_db_model,
    )
    mock_delete = mocker.patch("api.v1.workflows.delete_workflow_template_from_db")

    response = await fastapi_async_test_client.delete("/workflows/templates/1")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_create_workflow_template_invalid_workflow(
    fastapi_async_test_client, mocker, db
):
    """Test create workflow template route with invalid workflow ID."""

    db.get.return_value = None  # Simulate not finding workflow.

    request = {"display_name": "test template", "workflow_id": 1}

    response = await fastapi_async_test_client.post(
        "/workflows/templates/", json=request
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_create_workflow_signature_invalid_type(
    mocker, db: Session, regular_user: schemas.User, workflow_schema_mock
):
    """Test create_workflow_signature function with an invalid task type."""
    task_data = {"type": "invalid_type"}
    input_files = []
    output_path = ""
    with pytest.raises(ValueError):
        from lib.workflow_utils import create_workflow_signature

        create_workflow_signature(
            db, regular_user, task_data, input_files, output_path, workflow_schema_mock
        )


def test_replace_uuids_dict(mocker):
    data = {"uuid": "old_uuid", "nested": {"uuid": "nested_old_uuid"}}
    from lib.workflow_utils import replace_uuids

    replace_uuids(data)

    assert data["uuid"] != "old_uuid"
    assert data["nested"]["uuid"] != "nested_old_uuid"
    assert isinstance(data["uuid"], str)
    assert isinstance(data["nested"]["uuid"], str)


def test_replace_uuids_list(mocker):
    data = [{"uuid": "old_uuid"}, {"uuid": "another_old_uuid"}]
    from lib.workflow_utils import replace_uuids

    replace_uuids(data)
    assert data[0]["uuid"] != "old_uuid"
    assert data[1]["uuid"] != "another_old_uuid"

    assert isinstance(data[0]["uuid"], str)
    assert isinstance(data[1]["uuid"], str)


def test_replace_uuids_replace_with(mocker):
    data = {"uuid": "old_uuid"}
    replace_value = "new_uuid"

    from lib.workflow_utils import replace_uuids

    replace_uuids(data, replace_with=replace_value)
    assert data["uuid"] == replace_value


def test_get_task_signature(
    mocker, db, user_db_model, task_response, workflow_db_model
):
    """Test get_task_signature function."""

    mock_create_task_in_db = mocker.patch("lib.workflow_utils.create_task_in_db")
    mock_create_task_in_db.return_value = task_response

    mock_get_registered_tasks = mocker.patch("lib.workflow_utils.get_registered_tasks")
    mock_get_registered_tasks.return_value = [
        {"task_name": "test_task", "queue_name": "server_queue"}
    ]

    task_data = {
        "task_name": "test_task",
        "queue_name": "test_queue",
        "task_config": [{"name": "param1", "value": "value1"}],
        # A client-supplied uuid must never be trusted: task_data comes from
        # WorkflowRunRequest.workflow_spec, an unvalidated client dict, and
        # this value becomes the Celery task_id used as the Redis
        # result-backend key. Trusting it would let one tenant collide with
        # or overwrite another tenant's real, in-flight task result.
        "uuid": "attacker-supplied-uuid",
    }
    input_files = []
    output_path = "/tmp/output"


    task_signature = get_task_signature(
        db, user_db_model, task_data, input_files, output_path, workflow_db_model
    )

    assert isinstance(task_signature, Signature)
    assert task_signature.options.get("queue") == "server_queue"

    mock_create_task_in_db.assert_called_once()
    created_task = mock_create_task_in_db.call_args[0][1]
    assert created_task.display_name is None
    assert created_task.description is None
    # Always generated server-side, regardless of what task_data carried in.
    assert created_task.uuid != "attacker-supplied-uuid"
    assert len(created_task.uuid) == 32
    assert created_task.status_short == "PENDING"
    assert json.loads(created_task.config) == {"param1": "value1"}
    # The generated uuid is written back into task_data, so the caller's
    # in-memory spec tree (and, once run_workflow() re-serializes it after
    # dispatch) its persisted spec_json matches the DB task's uuid.
    assert task_data["uuid"] == created_task.uuid

    task_data["task_name"] = "malicious_task"
    with pytest.raises(ValueError):
        get_task_signature(
            db, user_db_model, task_data, input_files, output_path, workflow_db_model
        )


def test_create_workflow_signature_chain_multiple(
    mocker, db, regular_user, workflow_schema_mock
):
    """Test create_workflow_signature with a chain of multiple tasks."""
    task_data = {
        "type": "chain",
        "tasks": [
            {
                "type": "task",
                "task_name": "task1",
                "queue_name": "q1",
                "task_config": [],
                "tasks": [],
            },
            {
                "type": "task",
                "task_name": "task2",
                "queue_name": "q2",
                "task_config": [],
                "tasks": [],
            },
        ],
    }
    input_files = []
    output_path = ""

    mock_get_task_signature = mocker.patch("lib.workflow_utils.get_task_signature")
    mock_get_task_signature.return_value = mocker.MagicMock(spec=Signature)

    # Mock celery_group to consume the generator
    mocker.patch("lib.workflow_utils.celery_group", side_effect=lambda x: list(x))

    from lib.workflow_utils import create_workflow_signature

    sig = create_workflow_signature(
        db,
        regular_user,
        task_data,
        input_files,
        output_path,
        workflow_schema_mock,
    )

    assert sig is not None
    assert mock_get_task_signature.call_count == 2


def test_create_workflow_signature_chord(
    mocker, db, regular_user, workflow_schema_mock
):
    """Test create_workflow_signature with a chord."""
    task_data = {
        "type": "chord",
        "tasks": [
            {
                "type": "task",
                "task_name": "task1",
                "queue_name": "q1",
                "task_config": [],
                "tasks": [],
            }
        ],
        "callback": {
            "type": "task",
            "task_name": "callback_task",
            "queue_name": "q2",
            "task_config": [],
            "tasks": [],
        },
    }
    input_files = []
    output_path = ""

    mock_get_task_signature = mocker.patch("lib.workflow_utils.get_task_signature")
    mock_get_task_signature.return_value = mocker.MagicMock(spec=Signature)

    from lib.workflow_utils import create_workflow_signature

    sig = create_workflow_signature(
        db,
        regular_user,
        task_data,
        input_files,
        output_path,
        workflow_schema_mock,
    )

    assert sig is not None
    assert mock_get_task_signature.call_count == 2


def _create_mock_task(mocker, status_short):
    mock_task = mocker.MagicMock()
    mock_task.status_short = status_short
    mock_task.display_name = "Mock Task"
    mock_task.description = "Mock Description"
    mock_task.uuid = "3fa85f64-5717-4562-b3fc-2c963f66afa7"

    mock_user = mocker.MagicMock()
    mock_user.display_name = "Mock User"
    mock_user.username = "mockuser"
    mock_user.profile_picture_url = "http://localhost/profile/pic"
    mock_user.uuid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

    mock_task.user = mock_user
    return mock_task


def test_get_workflow_status_running(fastapi_test_client, mocker):
    """Test get_workflow_status returns RUNNING for STARTED status."""
    mock_workflow = mocker.MagicMock()
    mock_task = _create_mock_task(mocker, "STARTED")
    mock_workflow.tasks = [mock_task]

    mocker.patch("api.v1.workflows.get_workflow_with_access", return_value=mock_workflow)

    response = fastapi_test_client.get("/folders/1/workflows/1/status")
    assert response.status_code == 200
    assert response.json()["status"] == "RUNNING"


def test_get_workflow_status_pending(fastapi_test_client, mocker):
    """Test get_workflow_status returns PENDING when there are no tasks."""
    mock_workflow = mocker.MagicMock()
    mock_workflow.tasks = []

    mocker.patch("api.v1.workflows.get_workflow_with_access", return_value=mock_workflow)

    response = fastapi_test_client.get("/folders/1/workflows/1/status")
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"


def test_get_workflow_status_none_task_status(fastapi_test_client, mocker):
    """Test get_workflow_status returns RUNNING when a task has status_short None (e.g. mediator delay)."""
    mock_workflow = mocker.MagicMock()
    mock_task = _create_mock_task(mocker, None)
    mock_workflow.tasks = [mock_task]

    mocker.patch("api.v1.workflows.get_workflow_with_access", return_value=mock_workflow)

    response = fastapi_test_client.get("/folders/1/workflows/1/status")
    assert response.status_code == 200
    assert response.json()["status"] == "RUNNING"


def test_get_workflow_status_mixed_success_and_none(fastapi_test_client, mocker):
    """Test get_workflow_status returns RUNNING when 1 task is SUCCESS and 1 task is None."""
    mock_workflow = mocker.MagicMock()
    task1 = _create_mock_task(mocker, "SUCCESS")
    task2 = _create_mock_task(mocker, None)
    mock_workflow.tasks = [task1, task2]

    mocker.patch("api.v1.workflows.get_workflow_with_access", return_value=mock_workflow)

    response = fastapi_test_client.get("/folders/1/workflows/1/status")
    assert response.status_code == 200
    assert response.json()["status"] == "RUNNING"


def test_get_workflow_status_complete(fastapi_test_client, mocker):
    """Test get_workflow_status returns COMPLETE when all tasks are SUCCESS."""
    mock_workflow = mocker.MagicMock()
    task1 = _create_mock_task(mocker, "SUCCESS")
    task2 = _create_mock_task(mocker, "SUCCESS")
    mock_workflow.tasks = [task1, task2]

    mocker.patch("api.v1.workflows.get_workflow_with_access", return_value=mock_workflow)

    response = fastapi_test_client.get("/folders/1/workflows/1/status")
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETE"


def test_get_workflow_status_complete_with_failures(fastapi_test_client, mocker):
    """Test get_workflow_status returns COMPLETE_WITH_FAILURES when all tasks are finished and at least 1 failed."""
    mock_workflow = mocker.MagicMock()
    task1 = _create_mock_task(mocker, "SUCCESS")
    task2 = _create_mock_task(mocker, "FAILURE")
    mock_workflow.tasks = [task1, task2]

    mocker.patch("api.v1.workflows.get_workflow_with_access", return_value=mock_workflow)

    response = fastapi_test_client.get("/folders/1/workflows/1/status")
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETE_WITH_FAILURES"


def test_get_workflow_status_revoked(fastapi_test_client, mocker):
    """Test get_workflow_status returns COMPLETE when tasks are SUCCESS or REVOKED."""
    mock_workflow = mocker.MagicMock()
    task1 = _create_mock_task(mocker, "SUCCESS")
    task2 = _create_mock_task(mocker, "REVOKED")
    mock_workflow.tasks = [task1, task2]

    mocker.patch("api.v1.workflows.get_workflow_with_access", return_value=mock_workflow)

    response = fastapi_test_client.get("/folders/1/workflows/1/status")
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETE"


@pytest.fixture
def other_users_workflow(mocker, db):
    """The URL folder is the user's own, the workflow is in a folder they can't access."""
    own_folder = Folder(id=1)
    other_folder = Folder(id=2)
    other_workflow = Workflow(id=5, folder_id=2, folder=other_folder, spec_json="{}")

    def _get(model, object_id):
        return {Folder: own_folder, Workflow: other_workflow}.get(model)

    db.get.side_effect = _get
    mocker.patch(
        "datastores.sql.crud.authz.check_user_access",
        side_effect=lambda db, user, roles, folder=None, file=None: folder is own_folder,
    )
    return other_workflow


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", "/folders/1/workflows/5", None),
        ("patch", "/folders/1/workflows/5", {"display_name": "x"}),
        ("post", "/folders/1/workflows/5/copy/", None),
        ("delete", "/folders/1/workflows/5", None),
        ("post", "/folders/1/workflows/5/run/", {"workflow_spec": {}}),
        ("get", "/folders/1/workflows/5/status", None),
        ("get", "/folders/1/workflows/5/generate_name/", None),
        ("get", "/workflows/5", None),
        ("get", "/workflows/5/report/", None),
        ("post", "/workflows/templates/", {"display_name": "x", "workflow_id": 5}),
    ],
)
async def test_workflow_in_other_folder_denied(
    fastapi_async_test_client, mocker, other_users_workflow, method, path, body
):
    """A workflow can't be reached by putting a folder the user can access in the URL."""
    mock_delete = mocker.patch("api.v1.workflows.delete_workflow_from_db")
    mock_update = mocker.patch("api.v1.workflows.update_workflow_in_db")
    mock_run = mocker.patch("api.v1.workflows.workflow_utils.run_workflow")
    mock_create = mocker.patch("api.v1.workflows.create_workflow_in_db")
    mock_create_template = mocker.patch("api.v1.workflows.create_workflow_template_in_db")

    kwargs = {"json": body} if body is not None else {}
    response = await fastapi_async_test_client.request(method.upper(), path, **kwargs)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    for mock in (mock_delete, mock_update, mock_run, mock_create, mock_create_template):
        mock.assert_not_called()


@pytest.mark.asyncio
async def test_create_workflow_with_inaccessible_file(fastapi_async_test_client, mocker):
    """A workflow can't be created on files the user can't access."""
    _allow_file_access(mocker, has_access=False)
    mock_create = mocker.patch("lib.workflow_utils.create_workflow_in_db")

    response = await fastapi_async_test_client.post(
        "/folders/1/workflows/", json={"folder_id": 1, "file_ids": [7]}
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_create_workflow_with_deleted_file(fastapi_async_test_client, mocker):
    _allow_file_access(mocker, is_deleted=True)
    mock_create = mocker.patch("lib.workflow_utils.create_workflow_in_db")

    response = await fastapi_async_test_client.post(
        "/folders/1/workflows/", json={"folder_id": 1, "file_ids": [7]}
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_update_workflow_ignores_location_and_owner(
    fastapi_async_test_client, mocker, workflow_db_model, workflow_response
):
    """PATCH can't move a workflow to another folder or change who owns it."""
    mocker.patch("api.v1.workflows.get_workflow_with_access", return_value=workflow_db_model)
    mock_update = mocker.patch(
        "api.v1.workflows.update_workflow_in_db", return_value=workflow_response
    )

    response = await fastapi_async_test_client.patch(
        "/folders/1/workflows/1",
        json={"display_name": "renamed", "folder_id": 999, "user_id": 999, "file_ids": [999]},
    )

    assert response.status_code == 200
    updated = mock_update.call_args.args[1]
    assert updated.display_name == "renamed"
    assert updated.folder_id == workflow_db_model.folder_id
    assert updated.user_id == workflow_db_model.user_id
    assert 999 not in updated.file_ids


@pytest.fixture
def workflow_with_inaccessible_file(mocker, workflow_db_model):
    """A workflow the user can edit, with an input file they can't access."""
    mocker.patch("api.v1.workflows.get_workflow_with_access", return_value=workflow_db_model)
    other_file = mocker.MagicMock(id=7, is_deleted=False)
    workflow_db_model.files = [other_file]
    workflow_db_model.folder.parent = Folder(id=10)
    mocker.patch(
        "api.v1.workflows.check_user_access",
        side_effect=lambda db, user, roles, folder=None, file=None: file is not other_file,
    )
    return workflow_db_model


@pytest.mark.asyncio
async def test_run_workflow_with_inaccessible_file(
    fastapi_async_test_client, mocker, workflow_with_inaccessible_file
):
    """Access to a workflow's folder doesn't allow running it on files the user can't access."""
    mock_run = mocker.patch("api.v1.workflows.workflow_utils.run_workflow")

    response = await fastapi_async_test_client.post(
        "/folders/1/workflows/1/run/", json={"workflow_spec": {}}
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_copy_workflow_with_inaccessible_file(
    fastapi_async_test_client, mocker, workflow_with_inaccessible_file
):
    mock_create_subfolder = mocker.patch("api.v1.workflows.create_subfolder_in_db")
    mock_create = mocker.patch("api.v1.workflows.create_workflow_in_db")

    response = await fastapi_async_test_client.post("/folders/1/workflows/1/copy/")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    mock_create_subfolder.assert_not_called()
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_copy_workflow_without_access_to_parent_folder(
    fastapi_async_test_client, mocker, workflow_db_model
):
    """A copy can't be created in a parent folder the user can't edit."""
    mocker.patch("api.v1.workflows.get_workflow_with_access", return_value=workflow_db_model)
    parent_folder = Folder(id=10)
    workflow_db_model.folder.parent = parent_folder
    mocker.patch(
        "api.v1.workflows.check_user_access",
        side_effect=lambda db, user, roles, folder=None, file=None: folder is not parent_folder,
    )
    mock_create_subfolder = mocker.patch("api.v1.workflows.create_subfolder_in_db")
    mock_create = mocker.patch("api.v1.workflows.create_workflow_in_db")

    response = await fastapi_async_test_client.post("/folders/1/workflows/1/copy/")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    mock_create_subfolder.assert_not_called()
    mock_create.assert_not_called()
