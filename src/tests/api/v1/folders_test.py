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

"""Tests for folder endpoints."""

import pytest
import httpx

from datastores.sql.models.role import Role
from datastores.sql.models.user import User as UserSQLModel
from datastores.sql.models.group import Group as GroupSQLModel
from api.v1 import schemas


def test_get_root_folders(fastapi_test_client, mocker, folder_response_compact):
    """Test getting root folders."""
    mock_folders = [
        folder_response_compact.model_dump(mode="json"),
        folder_response_compact.model_dump(mode="json"),
    ]
    mock_get_root_folders_from_db = mocker.patch(
        "api.v1.folders.get_root_folders_from_db"
    )
    mock_get_root_folders_from_db.return_value = mock_folders
    response = fastapi_test_client.get("/folders/")
    assert response.status_code == 200
    assert response.json() == mock_folders


def test_get_shared_folders(fastapi_test_client, mocker, folder_response_compact):
    """Test getting shared folders."""
    mock_folders = [
        folder_response_compact.model_dump(mode="json"),
        folder_response_compact.model_dump(mode="json"),
    ]
    mock_get_shared_folders_from_db = mocker.patch(
        "api.v1.folders.get_shared_folders_from_db"
    )
    mock_get_shared_folders_from_db.return_value = mock_folders

    response = fastapi_test_client.get("/folders/shared/")
    assert response.status_code == 200
    assert response.json() == mock_folders


def test_get_subfolders(fastapi_test_client, mocker, folder_response_compact):
    parent_folder_id = 1
    mock_subfolders = [
        folder_response_compact.model_dump(mode="json"),
        folder_response_compact.model_dump(mode="json"),
    ]
    mock_get_subfolders = mocker.patch("api.v1.folders.get_subfolders_from_db")
    mock_get_subfolders.return_value = mock_subfolders
    response = fastapi_test_client.get(f"/folders/{parent_folder_id}/folders/")
    assert response.status_code == 200
    assert response.json() == mock_subfolders


@pytest.mark.asyncio
async def test_create_root_folder(fastapi_async_test_client, mocker, folder_response):
    mock_folder_create = mocker.patch("api.v1.folders.create_root_folder_in_db")
    mock_folder_create.return_value = folder_response
    request = {"display_name": "test folder"}
    response = await fastapi_async_test_client.post("/folders/", json=request)
    assert response.status_code == 201
    assert response.json() == folder_response.model_dump(mode="json")


@pytest.mark.asyncio
async def test_create_subfolder(fastapi_async_test_client, mocker, folder_response):
    """Test create subfolder route."""
    parent_folder_id = 1
    mock_create_subfolder = mocker.patch("api.v1.folders.create_subfolder_in_db")
    folder_response.display_name = "test subfolder"
    mock_create_subfolder.return_value = folder_response
    request = {"display_name": "test subfolder"}

    response = await fastapi_async_test_client.post(
        f"/folders/{parent_folder_id}/folders/", json=request
    )
    assert response.status_code == 201
    assert response.json() == folder_response.model_dump(mode="json")


@pytest.mark.asyncio
async def test_update_folder(
    fastapi_async_test_client, mocker, folder_response, folder_db_model
):
    """Test update an existing folder."""
    mock_get_folder = mocker.patch("api.v1.folders.get_folder_from_db")
    mock_get_folder.return_value = folder_db_model

    mock_update_folder = mocker.patch("api.v1.folders.update_folder_in_db")
    mock_update_folder.return_value = folder_response

    request = {"display_name": "updated folder name", "id": 1}

    response = await fastapi_async_test_client.patch("/folders/1", json=request)
    assert response.status_code == 200
    assert response.json() == folder_response.model_dump(mode="json")


def test_delete_folder(fastapi_test_client, mocker, db):
    """Test deleting a folder."""
    mock_delete_folder = mocker.patch("api.v1.folders.delete_folder_from_db")
    folder_id = 1

    response = fastapi_test_client.delete(f"/folders/{folder_id}")

    assert response.status_code == 204
    mock_delete_folder.assert_called_once_with(db, folder_id)


def test_share_folder(
    fastapi_test_client, mocker, db, folder_db_model, folder_response
):
    folder_id = 1
    mock_get_folder_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.id = folder_id  # Ensure the fixture's ID matches
    folder_db_model.is_deleted = False  # CRITICAL: Ensure folder is not deleted
    mock_get_folder_db.return_value = folder_db_model
    mock_group_role_exists = mocker.patch("api.v1.folders.group_role_exists")
    mock_group_role_exists.return_value = False
    mock_user_role_exists = mocker.patch("api.v1.folders.user_role_exists")
    mock_user_role_exists.return_value = False
    mock_user_1 = mocker.MagicMock(spec=UserSQLModel, id=1, username="user1")
    mock_user_2 = mocker.MagicMock(spec=UserSQLModel, id=2, username="user2")
    mock_user_admin = mocker.MagicMock(spec=UserSQLModel, id=10, username="admin")
    mock_user_test = mocker.MagicMock(spec=UserSQLModel, id=11, username="test")

    mock_get_user_from_db = mocker.patch("api.v1.folders.get_user_from_db")
    mock_get_user_from_db.side_effect = lambda db_session, user_id_val: {
        1: mock_user_1,
        2: mock_user_2,
    }.get(user_id_val)

    mock_get_user_by_username_from_db = mocker.patch(
        "api.v1.folders.get_user_by_username_from_db"
    )
    mock_get_user_by_username_from_db.side_effect = lambda db_session, username_val: {
        "admin": mock_user_admin,
        "test": mock_user_test,
    }.get(username_val)

    mock_group_3 = mocker.MagicMock(spec=GroupSQLModel, id=3, name="group3")
    mock_group_4 = mocker.MagicMock(spec=GroupSQLModel, id=4, name="group4")
    mock_group_everyone = mocker.MagicMock(spec=GroupSQLModel, id=20, name="Everyone")
    mock_group_test_group = mocker.MagicMock(
        spec=GroupSQLModel, id=21, name="test_group"
    )

    mock_get_group_from_db = mocker.patch("api.v1.folders.get_group_from_db")
    mock_get_group_from_db.side_effect = lambda db_session, group_id_val: {
        3: mock_group_3,
        4: mock_group_4,
    }.get(group_id_val)

    mock_get_group_by_name_from_db = mocker.patch(
        "api.v1.folders.get_group_by_name_from_db"
    )
    mock_get_group_by_name_from_db.side_effect = lambda db_session, name_val: {
        "Everyone": mock_group_everyone,
        "test_group": mock_group_test_group,
    }.get(name_val)

    # 3. Mock role existence checks to always return False (role does not exist yet)
    mocker.patch("api.v1.folders.user_role_exists", return_value=False)
    mocker.patch("api.v1.folders.group_role_exists", return_value=False)

    # 4. Mock role creation functions (already in the original test)
    mock_create_user_role = mocker.patch("api.v1.folders.create_user_role_in_db")
    mock_create_group_role = mocker.patch("api.v1.folders.create_group_role_in_db")

    request = schemas.FolderShareRequest(
        user_ids=[1, 2],
        group_ids=[3, 4],
        user_names=["admin", "test"],
        group_names=["Everyone", "test_group"],
        user_role=Role.EDITOR.value,  # Use enum value, e.g., "Editor"
        group_role=Role.VIEWER.value,  # Use enum value, e.g., "Viewer"
    )

    response = fastapi_test_client.post(
        f"/folders/{folder_id}/roles", json=request.model_dump()
    )

    assert response.status_code == 200
    assert response.json()["id"] == folder_id

    # Assert that create_user_role_in_db was called correctly
    mock_create_user_role.assert_any_call(
        db, Role.EDITOR.name, mock_user_1.id, folder_id=folder_id
    )
    mock_create_user_role.assert_any_call(
        db, Role.EDITOR.name, mock_user_2.id, folder_id=folder_id
    )
    mock_create_user_role.assert_any_call(
        db, Role.EDITOR.name, mock_user_admin.id, folder_id=folder_id
    )
    mock_create_user_role.assert_any_call(
        db, Role.EDITOR.name, mock_user_test.id, folder_id=folder_id
    )
    assert mock_create_user_role.call_count == 4

    # Assert that create_group_role_in_db was called correctly
    mock_create_group_role.assert_any_call(
        db, Role.VIEWER.name, mock_group_3.id, folder_id=folder_id
    )
    mock_create_group_role.assert_any_call(
        db, Role.VIEWER.name, mock_group_4.id, folder_id=folder_id
    )
    mock_create_group_role.assert_any_call(
        db, Role.VIEWER.name, mock_group_everyone.id, folder_id=folder_id
    )
    mock_create_group_role.assert_any_call(
        db, Role.VIEWER.name, mock_group_test_group.id, folder_id=folder_id
    )
    assert mock_create_group_role.call_count == 4


def test_get_my_folder_role(fastapi_test_client, mocker, folder_db_model):
    mock_get_folder = mocker.patch("api.v1.folders.get_folder_from_db")
    mock_get_folder.return_value = folder_db_model

    mock_check_user_access = mocker.patch("api.v1.folders.check_user_access")
    mock_check_user_access.return_value = Role.OWNER

    folder_id = 1
    response = fastapi_test_client.get(f"/folders/{folder_id}/roles/me")

    assert response.status_code == 200
    assert response.json() == Role.OWNER.value
    mock_check_user_access.assert_called_once()


def test_get_my_folder_role_value_error(fastapi_test_client, mocker, folder_db_model):
    """Test get_my_folder_role when check_user_access raises ValueError."""
    mock_get_folder = mocker.patch("api.v1.folders.get_folder_from_db")
    mock_get_folder.return_value = folder_db_model

    mock_check_user_access = mocker.patch("api.v1.folders.check_user_access")
    mock_check_user_access.side_effect = ValueError("Folder access error")

    folder_id = 1
    response = fastapi_test_client.get(f"/folders/{folder_id}/roles/me")

    assert response.status_code == 404
    assert response.json()["detail"] == "Folder access error"


def test_delete_group_role(fastapi_test_client, mocker, db):

    mock_delete_group_role_from_db = mocker.patch(
        "api.v1.folders.delete_group_role_from_db"
    )
    folder_id = 1
    role_id = 2

    response = fastapi_test_client.delete(
        f"/folders/{folder_id}/roles/groups/{role_id}"
    )

    assert response.status_code == 200
    mock_delete_group_role_from_db.assert_called_once_with(db, role_id)


def test_delete_user_role(fastapi_test_client, mocker, db):
    mock_delete_user_role_from_db = mocker.patch(
        "api.v1.folders.delete_user_role_from_db"
    )
    folder_id = 1
    role_id = 2

    response = fastapi_test_client.delete(f"/folders/{folder_id}/roles/users/{role_id}")

    assert response.status_code == 200
    mock_delete_user_role_from_db.assert_called_once_with(db, role_id)


def test_get_folder_files(fastapi_test_client, mocker, file_response_compact_list):
    """Test getting files for a folder."""
    folder_id = 1
    mock_files = [
        file_response_compact_list.model_dump(mode="json"),
        file_response_compact_list.model_dump(mode="json"),
    ]
    mock_get_files_from_db = mocker.patch("api.v1.folders.get_files_from_db")
    mock_get_files_from_db.return_value = mock_files

    response = fastapi_test_client.get(f"/folders/{folder_id}/files/")
    assert response.status_code == 200
    assert response.json() == mock_files


def test_get_folder_success(fastapi_test_client, mocker):
    """Test get_folder returns success."""
    import uuid

    mock_folder = mocker.MagicMock()
    mock_folder.is_deleted = False
    mock_folder.id = 1
    mock_folder.display_name = "Test Folder"
    mock_folder.description = "Test Description"
    mock_folder.uuid = uuid.uuid4()
    mock_folder.parent = None
    mock_folder.selectable = False
    mock_folder.workflows = []
    mock_folder.user_roles = []
    mock_folder.group_roles = []
    mock_folder.storage_provider = "local"

    mock_user = mocker.MagicMock()
    mock_user.display_name = "Test User"
    mock_user.username = "testuser"
    mock_user.profile_picture_url = None
    mock_user.uuid = uuid.uuid4()
    mock_folder.user = mock_user

    mocker.patch("api.v1.folders.get_folder_from_db", return_value=mock_folder)

    response = fastapi_test_client.get("/folders/1")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Test Folder"


def test_get_folder_not_found(fastapi_test_client, mocker):
    """Test get_folder returns 404 when folder not found."""
    mocker.patch("api.v1.folders.get_folder_from_db", return_value=None)

    response = fastapi_test_client.get("/folders/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Folder not found."


def test_get_folder_deleted(fastapi_test_client, mocker):
    """Test get_folder returns 404 when folder is deleted."""
    mock_folder = mocker.MagicMock()
    mock_folder.is_deleted = True
    mocker.patch("api.v1.folders.get_folder_from_db", return_value=mock_folder)

    response = fastapi_test_client.get("/folders/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Folder is deleted."


def test_get_folder_value_error(fastapi_test_client, mocker):
    """Test get_folder returns 404 on ValueError."""
    mocker.patch(
        "api.v1.folders.get_folder_from_db", side_effect=ValueError("Invalid ID")
    )

    response = fastapi_test_client.get("/folders/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Invalid ID"


def test_share_folder_not_found(fastapi_test_client, mocker):
    """Test share_folder when folder not found."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    mock_get_folder_from_db.return_value = None
    folder_id = 1

    request = {"user_ids": [1], "user_role": "Viewer"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 404
    assert response.json()["detail"] == "Folder not found."


def test_share_folder_deleted(fastapi_test_client, mocker, folder_db_model):
    """Test share_folder when folder is deleted."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = True
    mock_get_folder_from_db.return_value = folder_db_model
    folder_id = 1

    request = {"user_ids": [1], "user_role": "Viewer"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 404
    assert response.json()["detail"] == "Cannot share a deleted folder."


def test_share_folder_user_not_found(fastapi_test_client, mocker, folder_db_model):
    """Test share_folder when user not found."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mock_get_user_from_db = mocker.patch("api.v1.folders.get_user_from_db")
    mock_get_user_from_db.return_value = None

    folder_id = 1
    request = {"user_ids": [999], "user_role": "Viewer"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 404
    assert "User with ID 999 not found" in response.json()["detail"]


def test_share_folder_invalid_role(fastapi_test_client, mocker, folder_db_model):
    """Test share_folder with invalid role."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    folder_id = 1
    request = {"user_ids": [1], "user_role": "INVALID_ROLE"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 400
    assert "Invalid role provided" in response.json()["detail"]


def test_share_folder_user_role_exists(fastapi_test_client, mocker, folder_db_model):
    """Test share_folder when user already has the role."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mock_get_user_from_db = mocker.patch("api.v1.folders.get_user_from_db")
    mock_get_user_from_db.return_value = mocker.MagicMock()

    mock_user_role_exists = mocker.patch("api.v1.folders.user_role_exists")
    mock_user_role_exists.return_value = True

    folder_id = 1
    request = {"user_ids": [1], "user_role": "Viewer"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 409
    assert "already has the role" in response.json()["detail"]


def test_share_folder_username_not_found(fastapi_test_client, mocker, folder_db_model):
    """Test share_folder when user by username not found."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mock_get_user_by_username = mocker.patch(
        "api.v1.folders.get_user_by_username_from_db"
    )
    mock_get_user_by_username.return_value = None

    folder_id = 1
    request = {"user_names": ["nonexistent"], "user_role": "Viewer"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 404
    assert "User with username 'nonexistent' not found" in response.json()["detail"]


def test_share_folder_username_role_exists(
    fastapi_test_client, mocker, folder_db_model
):
    """Test share_folder when user by username already has the role."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mock_user = mocker.MagicMock()
    mock_user.id = 1
    mock_get_user_by_username = mocker.patch(
        "api.v1.folders.get_user_by_username_from_db"
    )
    mock_get_user_by_username.return_value = mock_user

    mock_user_role_exists = mocker.patch("api.v1.folders.user_role_exists")
    mock_user_role_exists.return_value = True

    folder_id = 1
    request = {"user_names": ["testuser"], "user_role": "Viewer"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 409
    assert "already has the role" in response.json()["detail"]


def test_share_folder_group_not_found(fastapi_test_client, mocker, folder_db_model):
    """Test share_folder when group not found."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mock_get_group_from_db = mocker.patch("api.v1.folders.get_group_from_db")
    mock_get_group_from_db.return_value = None

    folder_id = 1
    request = {"group_ids": [999], "group_role": "Viewer"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 404
    assert "Group with ID 999 not found" in response.json()["detail"]


def test_share_folder_group_role_exists(fastapi_test_client, mocker, folder_db_model):
    """Test share_folder when group already has the role."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mock_get_group_from_db = mocker.patch("api.v1.folders.get_group_from_db")
    mock_get_group_from_db.return_value = mocker.MagicMock()

    mock_group_role_exists = mocker.patch("api.v1.folders.group_role_exists")
    mock_group_role_exists.return_value = True

    folder_id = 1
    request = {"group_ids": [1], "group_role": "Viewer"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 409
    assert "already has the role" in response.json()["detail"]


def test_share_folder_group_by_name_not_found(
    fastapi_test_client, mocker, folder_db_model
):
    """Test share_folder when group by name not found."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mock_get_group_by_name = mocker.patch("api.v1.folders.get_group_by_name_from_db")
    mock_get_group_by_name.return_value = None

    folder_id = 1
    request = {"group_names": ["nonexistent"], "group_role": "Viewer"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 404
    assert "Group with name 'nonexistent' not found" in response.json()["detail"]


def test_share_folder_group_by_name_role_exists(
    fastapi_test_client, mocker, folder_db_model
):
    """Test share_folder when group by name already has the role."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mock_group = mocker.MagicMock()
    mock_group.id = 1
    mock_get_group_by_name = mocker.patch("api.v1.folders.get_group_by_name_from_db")
    mock_get_group_by_name.return_value = mock_group

    mock_group_role_exists = mocker.patch("api.v1.folders.group_role_exists")
    mock_group_role_exists.return_value = True

    folder_id = 1
    request = {"group_names": ["testgroup"], "group_role": "Viewer"}
    response = fastapi_test_client.post(f"/folders/{folder_id}/roles", json=request)
    assert response.status_code == 409
    assert "already has the role" in response.json()["detail"]


def test_start_investigation_no_adk_url(fastapi_test_client, mocker, folder_db_model):
    """Test start_investigation when ADK URL is not configured."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    mock_get_folder_from_db.return_value = folder_db_model

    # Mock config.config
    mocker.patch("api.v1.folders.config.config", {})  # Empty dict

    folder_id = 1
    request_data = {
        "session_id": "test_session",
        "agent_name": "test_agent",
        "user_message": "test question",
    }
    response = fastapi_test_client.post(
        f"/folders/{folder_id}/investigations/run", json=request_data
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "ADK server URL is not configured."


@pytest.mark.asyncio
async def test_start_investigation_success(
    fastapi_async_test_client, mocker, folder_db_model
):
    """Test start_investigation success."""
    mock_get_folder = mocker.patch("api.v1.folders.get_folder_from_db")
    mock_get_folder.return_value = folder_db_model

    # Mock config
    mocker.patch(
        "api.v1.folders.config.config",
        {"experiments": {"agents": {"adk_server_url": "http://mock-adk"}}},
    )

    # Mock stream manager
    mock_stream_manager = mocker.patch("api.v1.folders.stream_manager")
    mock_session = mocker.MagicMock()
    mock_stream_manager.get_session.return_value = None  # New session
    mock_stream_manager.create_session.return_value = mock_session

    # Mock httpx.AsyncClient
    mock_async_client = mocker.patch("api.v1.folders.httpx.AsyncClient")
    mock_client_instance = mocker.MagicMock()
    mock_async_client.return_value.__aenter__.return_value = mock_client_instance

    mock_response = mocker.MagicMock()
    mock_response.raise_for_status.return_value = None

    # Mock async iterator for response.aiter_bytes()
    async def mock_aiter_bytes():
        yield b'data: {"type": "message", "message": "hello"}\n'
        yield b'data: {"type": "complete", "message": "done"}\n'

    mock_response.aiter_bytes.return_value = mock_aiter_bytes()

    # Mock the context manager for client.stream
    class MockStreamContextManager:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_client_instance.stream.return_value = MockStreamContextManager()

    folder_id = 1
    request_data = {
        "session_id": "test_session",
        "agent_name": "test_agent",
        "user_message": "test question",
    }

    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/investigations/run", json=request_data
    )

    assert response.status_code == 200


def test_create_adk_session_no_adk_url(fastapi_test_client, mocker, folder_db_model):
    """Test create_adk_session when ADK URL is not configured."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    mock_get_folder_from_db.return_value = folder_db_model

    # Mock config.config
    mocker.patch("api.v1.folders.config.config", {})  # Empty dict

    folder_id = 1
    request_data = {"context": "test context"}
    response = fastapi_test_client.post(
        f"/folders/{folder_id}/investigations/init", json=request_data
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "ADK server URL is not configured."


@pytest.mark.asyncio
async def test_create_adk_session_success(
    fastapi_async_test_client, mocker, folder_db_model
):
    """Test create_adk_session success."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mocker.patch(
        "api.v1.folders.config.config",
        {"experiments": {"agents": {"adk_server_url": "http://mock-adk"}}},
    )

    class MockFile:

        def __init__(self, display_name, magic_mime, magic_text):
            self.display_name = display_name
            self.magic_mime = magic_mime
            self.magic_text = magic_text

    mocker.patch(
        "api.v1.folders.get_files_from_db",
        return_value=[MockFile("test.txt", "text/plain", "ASCII text")],
    )

    mock_payload = mocker.MagicMock()
    mock_payload.dict.return_value = {"initial": "state"}
    mocker.patch("api.v1.folders.generate_initial_state", return_value=mock_payload)

    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mocker.patch("api.v1.folders.httpx.post", return_value=mock_response)

    import uuid

    mock_uuid_obj = uuid.UUID("12345678-1234-5678-1234-567812345678")
    mock_uuid = mocker.patch("api.v1.folders.uuid.uuid4")
    mock_uuid.return_value = mock_uuid_obj

    folder_id = 1
    request_data = {"context": "test context"}
    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/investigations/init", json=request_data
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "12345678-1234-5678-1234-567812345678"


def test_get_all_folders(fastapi_test_client, mocker, folder_response_compact):
    """Test getting all folders."""
    mock_folders = [
        folder_response_compact.model_dump(mode="json"),
        folder_response_compact.model_dump(mode="json"),
    ]
    mock_get_all_folders_from_db = mocker.patch(
        "api.v1.folders.get_all_folders_from_db"
    )
    mock_get_all_folders_from_db.return_value = (mock_folders, 2)

    response = fastapi_test_client.get("/folders/all/")
    assert response.status_code == 200
    assert response.json()["folders"] == mock_folders
    assert response.json()["total_count"] == 2


@pytest.mark.asyncio
async def test_create_adk_session_status_error(
    fastapi_async_test_client, mocker, folder_db_model
):
    """Test create_adk_session with HTTPStatusError."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mocker.patch(
        "api.v1.folders.config.config",
        {"experiments": {"agents": {"adk_server_url": "http://mock-adk"}}},
    )
    mocker.patch("api.v1.folders.get_files_from_db", return_value=[])

    mock_payload = mocker.MagicMock()
    mock_payload.dict.return_value = {"initial": "state"}
    mocker.patch("api.v1.folders.generate_initial_state", return_value=mock_payload)

    def raise_status_error(*args, **kwargs):
        mock_resp = mocker.MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Error"
        raise httpx.HTTPStatusError(
            "Mock error", request=mocker.MagicMock(), response=mock_resp
        )

    mocker.patch("api.v1.folders.httpx.post", side_effect=raise_status_error)

    import uuid

    mock_uuid_obj = uuid.UUID("12345678-1234-5678-1234-567812345678")
    mocker.patch("api.v1.folders.uuid.uuid4", return_value=mock_uuid_obj)

    folder_id = 1
    request_data = {"context": "test context"}
    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/investigations/init", json=request_data
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "12345678-1234-5678-1234-567812345678"


@pytest.mark.asyncio
async def test_create_adk_session_request_error(
    fastapi_async_test_client, mocker, folder_db_model
):
    """Test create_adk_session with RequestError."""
    mock_get_folder_from_db = mocker.patch("api.v1.folders.get_folder_from_db")
    folder_db_model.is_deleted = False
    mock_get_folder_from_db.return_value = folder_db_model

    mocker.patch(
        "api.v1.folders.config.config",
        {"experiments": {"agents": {"adk_server_url": "http://mock-adk"}}},
    )
    mocker.patch("api.v1.folders.get_files_from_db", return_value=[])

    mock_payload = mocker.MagicMock()
    mock_payload.dict.return_value = {"initial": "state"}
    mocker.patch("api.v1.folders.generate_initial_state", return_value=mock_payload)

    def raise_request_error(*args, **kwargs):
        raise httpx.RequestError("Connection failed", request=mocker.MagicMock())

    mocker.patch("api.v1.folders.httpx.post", side_effect=raise_request_error)

    import uuid

    mock_uuid_obj = uuid.UUID("12345678-1234-5678-1234-567812345678")
    mocker.patch("api.v1.folders.uuid.uuid4", return_value=mock_uuid_obj)

    folder_id = 1
    request_data = {"context": "test context"}
    response = await fastapi_async_test_client.post(
        f"/folders/{folder_id}/investigations/init", json=request_data
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "12345678-1234-5678-1234-567812345678"


@pytest.mark.asyncio
async def test_get_adk_sse_session_success(mocker):
    """Test get_adk_sse_session success by calling it directly."""
    from api.v1.folders import get_adk_sse_session

    mocker.patch(
        "api.v1.folders.config.config",
        {"experiments": {"agents": {"adk_server_url": "http://mock-adk"}}},
    )

    # Mock sleep to not wait
    mocker.patch("api.v1.folders.asyncio.sleep", return_value=None)

    mock_async_client = mocker.patch("api.v1.folders.httpx.AsyncClient")
    mock_client_instance = mocker.AsyncMock()
    mock_async_client.return_value.__aenter__.return_value = mock_client_instance

    mock_response = mocker.MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"status": "running"}

    # First call succeeds, second raises RequestError to break loop
    mock_client_instance.get.side_effect = [
        mock_response,
        httpx.RequestError("Connection failed", request=mocker.MagicMock()),
    ]

    # Mock dependencies
    mock_db = mocker.MagicMock()
    mock_user = mocker.MagicMock()
    mock_user.id = 1

    response = await get_adk_sse_session(
        folder_id=1, session_id="test_session", db=mock_db, current_user=mock_user
    )

    # response is an EventSourceResponse
    # We can iterate over its body_iterator
    results = []
    try:
        async for item in response.body_iterator:
            results.append(item)
    except Exception:
        pass

    assert len(results) > 0
    assert "running" in results[0]
