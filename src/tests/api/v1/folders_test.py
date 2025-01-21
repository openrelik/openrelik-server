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


def test_share_folder(fastapi_test_client, mocker, db):
    mock_create_user_role = mocker.patch("api.v1.folders.create_user_role_in_db")
    mock_create_group_role = mocker.patch("api.v1.folders.create_group_role_in_db")
    folder_id = 1
    request = schemas.FolderShareRequest(
        user_ids=[1, 2], group_ids=[3, 4], user_role=Role.OWNER, group_role=Role.OWNER
    )

    response = fastapi_test_client.post(
        f"/folders/{folder_id}/roles", json=request.model_dump()
    )

    assert response.status_code == 200
    mock_create_user_role.assert_any_call(db, Role.OWNER, 2, folder_id)
    mock_create_user_role.assert_any_call(db, Role.OWNER, 1, folder_id)
    mock_create_group_role.assert_any_call(db, Role.OWNER, 4, folder_id)
    mock_create_group_role.assert_any_call(db, Role.OWNER, 3, folder_id)


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
