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
    mock_folder_create = mocker.patch(
        "api.v1.folders.create_root_folder_in_db")
    mock_folder_create.return_value = folder_response
    request = {"display_name": "test folder"}
    response = await fastapi_async_test_client.post("/folders/", json=request)
    assert response.status_code == 201
    assert response.json() == folder_response.model_dump(mode="json")


@pytest.mark.asyncio
async def test_create_subfolder(fastapi_async_test_client, mocker, folder_response):
    """Test create subfolder route."""
    parent_folder_id = 1
    mock_create_subfolder = mocker.patch(
        "api.v1.folders.create_subfolder_in_db")
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


def test_share_folder(fastapi_test_client, mocker, db, folder_db_model, folder_response):
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
    mock_user_admin = mocker.MagicMock(
        spec=UserSQLModel, id=10, username="admin")
    mock_user_test = mocker.MagicMock(
        spec=UserSQLModel, id=11, username="test")

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
    mock_group_everyone = mocker.MagicMock(
        spec=GroupSQLModel, id=20, name="Everyone")
    mock_group_test_group = mocker.MagicMock(
        spec=GroupSQLModel, id=21, name="test_group")

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
    mock_create_user_role = mocker.patch(
        "api.v1.folders.create_user_role_in_db")
    mock_create_group_role = mocker.patch(
        "api.v1.folders.create_group_role_in_db")

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
        db, Role.EDITOR.name, mock_user_1.id, folder_id=folder_id)
    mock_create_user_role.assert_any_call(
        db, Role.EDITOR.name, mock_user_2.id, folder_id=folder_id)
    mock_create_user_role.assert_any_call(
        db, Role.EDITOR.name, mock_user_admin.id, folder_id=folder_id)
    mock_create_user_role.assert_any_call(
        db, Role.EDITOR.name, mock_user_test.id, folder_id=folder_id)
    assert mock_create_user_role.call_count == 4

    # Assert that create_group_role_in_db was called correctly
    mock_create_group_role.assert_any_call(
        db, Role.VIEWER.name, mock_group_3.id, folder_id=folder_id)
    mock_create_group_role.assert_any_call(
        db, Role.VIEWER.name, mock_group_4.id, folder_id=folder_id)
    mock_create_group_role.assert_any_call(
        db, Role.VIEWER.name, mock_group_everyone.id, folder_id=folder_id)
    mock_create_group_role.assert_any_call(
        db, Role.VIEWER.name, mock_group_test_group.id, folder_id=folder_id)
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

    response = fastapi_test_client.delete(
        f"/folders/{folder_id}/roles/users/{role_id}")

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
