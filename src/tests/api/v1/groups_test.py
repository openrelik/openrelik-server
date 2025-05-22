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
"""Tests for groups endpoints."""

import uuid
from datastores.sql.models.group import Group as GroupSQLModel  # Import Group model
import json
from unittest.mock import MagicMock

from datastores.sql.models.user import User as UserSQLModel


def test_get_all_groups(fastapi_test_client, db, example_groups):
    """Test the get_all_groups endpoint."""
    db.query.return_value.all.return_value = example_groups
    response = fastapi_test_client.get("/groups/")
    groups = response.json()

    assert response.status_code == 200
    assert len(groups) == 2
    assert groups[0]["name"] == "Group 1"
    assert groups[0]["description"] == "Description 1"
    assert groups[0]["id"] == 1  # Now you can assert on ID
    assert groups[1]["name"] == "Group 2"
    assert groups[1]["description"] == "Description 2"
    assert groups[1]["id"] == 2


def test_create_group_with_users(fastapi_test_client, db, mocker):
    """Test the create_group endpoint."""
    # Mock the check for existing group
    # db.query.return_value.filter.return_value.first.return_value = None

    # Mock the user lookups within create_group_in_db and add_users_to_group
    mock_user_test = MagicMock(spec=UserSQLModel)
    mock_user_test.username = "test"
    mock_user_test_groups_collection = MagicMock(spec=list)
    mock_user_test.groups = mock_user_test_groups_collection
    mock_user_test._sa_instance_state = MagicMock()
    mock_user_test._sa_instance_state.manager.initialize_collection.return_value = (
        MagicMock(),
        mock_user_test_groups_collection,
    )

    mock_user_test2 = MagicMock(spec=UserSQLModel)
    mock_user_test2.username = "test2"
    mock_user_test2_groups_collection = MagicMock(spec=list)
    mock_user_test2.groups = mock_user_test2_groups_collection
    mock_user_test2._sa_instance_state = MagicMock()
    mock_user_test2._sa_instance_state.manager.initialize_collection.return_value = (
        MagicMock(),
        mock_user_test2_groups_collection,
    )

    mock_user_query_result = {
        "test": mock_user_test,
        "test2": mock_user_test2,
    }

    # Store the original db.query
    original_db_query = db.query

    def query_side_effect(model):
        if model.__name__ == "Group":
            mock_group_query = MagicMock()
            mock_group_query.filter.return_value.first.return_value = (
                None  # No existing group
            )
            return mock_group_query
        elif model.__name__ == "User":
            mock_user_query = MagicMock()
            # Simulate filter by username: User.username == value
            mock_user_query.filter.side_effect = lambda expr: MagicMock(
                first=MagicMock(
                    return_value=mock_user_query_result.get(expr.right.value)
                )
            )
            return mock_user_query
        return original_db_query(model)  # Call original for other models

    db.query.side_effect = query_side_effect

    db.commit.return_value = None
    db.refresh.return_value = None
    group_data = {
        "name": "New Group",
        "description": "New Description",
        "users": ["test", "test2"],
    }

    response = fastapi_test_client.post("/groups/", json=group_data)
    created_group = response.json()

    assert response.status_code == 201
    assert created_group["name"] == "New Group"
    assert created_group["description"] == "New Description"
    # The endpoint calls create_group_in_db (adds group, commits, refreshes)
    # Then calls add_users_to_group (commits, refreshes)
    db.add.assert_called_once()
    assert db.commit.call_count == 2
    assert db.refresh.call_count == 2


def test_create_group(fastapi_test_client, db, example_groups):
    """Test the create_group endpoint with users."""
    db.query.return_value.filter.return_value.first.return_value = (
        None  # No existing group
    )
    db.commit.return_value = None
    db.refresh.return_value = None

    group_data = {
        "name": "New Group",
        "description": "New Description",
    }

    response = fastapi_test_client.post("/groups/", json=group_data)
    created_group = response.json()

    assert response.status_code == 201
    assert created_group["name"] == "New Group"
    assert created_group["description"] == "New Description"
    db.add.assert_called_once()
    assert db.commit.call_count == 1  # Only one commit if no users to add


def test_create_group_with_existing_name(fastapi_test_client, db, example_groups):
    """Test the create_group endpoint with an existing name."""
    db.query.return_value.filter.return_value.first.return_value = example_groups[0]
    db.commit.return_value = None
    db.refresh.return_value = None

    group_data = {
        "name": "Group 1",  # This name already exists in example_groups
        "description": "New Description",
        "users": ["user1_uname", "user2_uname"],
    }

    response = fastapi_test_client.post("/groups/", json=group_data)
    assert response.status_code == 400
    assert response.json() == {"detail": "Group with name Group 1 already exists."}


def test_get_group_users(fastapi_test_client, db, example_groups):
    """Test the get_group_users endpoint."""
    db.query.return_value.filter.return_value.first.return_value = example_groups[0]
    # The line above was problematic. example_groups[0] now has users populated by the fixture.

    response = fastapi_test_client.get("/groups/Group 1/users")
    users_response = response.json()

    assert response.status_code == 200
    assert len(users_response) == 2

    # Assertions for the first user (example_user_1)
    # Ensure these match the UserResponse schema and data in example_user_1
    assert users_response[0]["id"] == 1
    assert users_response[0]["display_name"] == "User 1"
    assert users_response[0]["username"] == "user1_uname"
    assert users_response[0]["email"] == "user1@example.com"

    # Assertions for the second user (example_user_2)
    assert users_response[1]["id"] == 2
    assert users_response[1]["display_name"] == "User 2"
    assert users_response[1]["username"] == "user2_uname"
    assert users_response[1]["email"] == "user2@example.com"


def test_get_group_users_not_found(fastapi_test_client, db):
    """Test the get_group_users endpoint when group is not found."""
    db.query.return_value.filter.return_value.first.return_value = None

    response = fastapi_test_client.get("/groups/NonExistentGroup/users")
    assert response.status_code == 404
    assert response.json() == {"detail": "Group with name NonExistentGroup not found."}


def test_add_users_to_group(fastapi_test_client, db, example_groups, mocker):
    """Test the add_users_to_group endpoint."""
    mock_group = example_groups[0]
    mock_group.users = MagicMock(spec=list)  # Ensure users attribute is a mock list

    # Mock users to be added - these need full attributes for UserResponse
    mock_user_to_add_1 = MagicMock(spec=UserSQLModel)
    mock_user_to_add_1.id = 101
    mock_user_to_add_1.display_name = "Added User 1"
    mock_user_to_add_1.username = "added_user1_uname"
    mock_user_to_add_1.email = "added1@example.com"
    mock_user_to_add_1.auth_method = "test_auth"
    mock_user_to_add_1.profile_picture_url = None
    mock_user_to_add_1.uuid = uuid.uuid4()
    mock_user_to_add_1.is_admin = False
    mock_user_to_add_1_groups_collection = MagicMock(spec=list)
    mock_user_to_add_1.groups = mock_user_to_add_1_groups_collection
    mock_user_to_add_1._sa_instance_state = MagicMock()
    mock_user_to_add_1._sa_instance_state.manager.initialize_collection.return_value = (
        MagicMock(),
        mock_user_to_add_1_groups_collection,
    )

    mock_user_to_add_2 = MagicMock(spec=UserSQLModel)
    mock_user_to_add_2.id = 102
    mock_user_to_add_2.display_name = "Added User 2"
    mock_user_to_add_2.username = "added_user2_uname"
    mock_user_to_add_2.email = "added2@example.com"
    mock_user_to_add_2.auth_method = "test_auth"
    mock_user_to_add_2.profile_picture_url = None
    mock_user_to_add_2.uuid = uuid.uuid4()
    mock_user_to_add_2.is_admin = False
    mock_user_to_add_2_groups_collection = MagicMock(spec=list)
    mock_user_to_add_2.groups = mock_user_to_add_2_groups_collection
    mock_user_to_add_2._sa_instance_state = MagicMock()
    mock_user_to_add_2._sa_instance_state.manager.initialize_collection.return_value = (
        MagicMock(),
        mock_user_to_add_2_groups_collection,
    )

    mock_user_query_results = {
        "added_user1_uname": mock_user_to_add_1,
        "added_user2_uname": mock_user_to_add_2,
    }

    original_db_query = db.query

    def query_side_effect(model):
        if model.__name__ == "Group":
            mock_group_query = MagicMock()
            mock_group_query.filter.return_value.first.return_value = mock_group
            return mock_group_query
        elif model.__name__ == "User":
            mock_user_query = MagicMock()
            mock_user_query.filter.side_effect = lambda expr: MagicMock(
                first=MagicMock(
                    return_value=mock_user_query_results.get(expr.right.value)
                )
            )
            return mock_user_query
        return original_db_query(model)

    db.query.side_effect = query_side_effect

    db.commit.return_value = None
    db.refresh.return_value = None

    user_usernames_to_add = ["added_user1_uname", "added_user2_uname"]
    response = fastapi_test_client.post(
        f"/groups/{mock_group.name}/users", json=user_usernames_to_add
    )
    added_users_response = response.json()

    assert response.status_code == 200
    assert len(added_users_response) == 2

    # Assertions for the first added user
    assert added_users_response[0]["id"] == mock_user_to_add_1.id
    assert added_users_response[0]["display_name"] == mock_user_to_add_1.display_name
    assert added_users_response[0]["username"] == mock_user_to_add_1.username

    # Assertions for the second added user
    assert added_users_response[1]["id"] == mock_user_to_add_2.id
    assert added_users_response[1]["display_name"] == mock_user_to_add_2.display_name
    assert added_users_response[1]["username"] == mock_user_to_add_2.username

    assert db.commit.call_count == 1
    assert db.refresh.call_count == 1


def test_add_users_to_group_with_nonexistent_user(
    fastapi_test_client, db, example_groups, mocker
):
    """Test the add_users_to_group endpoint with a nonexistent user."""
    mock_group = example_groups[0]

    # Mock user lookup: one exists, one doesn't
    mock_existing_user = MagicMock(spec=UserSQLModel)
    mock_existing_user.username = "existing_user"
    mock_existing_user_groups_collection = MagicMock(spec=list)
    mock_existing_user.groups = mock_existing_user_groups_collection
    mock_existing_user._sa_instance_state = MagicMock()
    mock_existing_user._sa_instance_state.manager.initialize_collection.return_value = (
        MagicMock(),
        mock_existing_user_groups_collection,
    )

    mock_user_query_results = {
        "existing_user": mock_existing_user,
        "nonexistent_user": None,
    }

    original_db_query = db.query

    def query_side_effect(model):
        if model.__name__ == "Group":
            mock_group_query = MagicMock()
            mock_group_query.filter.return_value.first.return_value = mock_group
            return mock_group_query
        elif model.__name__ == "User":
            mock_user_query = MagicMock()
            mock_user_query.filter.side_effect = lambda expr: MagicMock(
                first=MagicMock(
                    return_value=mock_user_query_results.get(expr.right.value)
                )
            )
            return mock_user_query
        return original_db_query(model)

    db.query.side_effect = query_side_effect

    db.commit.return_value = None
    db.refresh.return_value = None

    user_usernames_to_add = ["existing_user", "nonexistent_user"]
    response = fastapi_test_client.post(
        f"/groups/{mock_group.name}/users", json=user_usernames_to_add
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "User with username nonexistent_user not found."
    }
    db.commit.assert_not_called()
    db.refresh.assert_not_called()


def test_add_users_to_group_not_found(fastapi_test_client, db):
    """Test the add_users_to_group endpoint when group is not found."""
    db.query.return_value.filter.return_value.first.return_value = None

    user_ids_to_add = ["test_user", "test_user1"]
    response = fastapi_test_client.post(
        "/groups/NonExistentGroup/users", json=user_ids_to_add
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Group with name NonExistentGroup not found."}


def test_remove_users_from_group(fastapi_test_client, db, example_groups, mocker):
    """Test the remove_users_from_group endpoint."""
    mock_group = MagicMock(spec=GroupSQLModel)  # Use a fresh mock for the group
    mock_group.name = "GroupForRemoveTest"

    mock_user_to_remove = MagicMock(spec=UserSQLModel)
    mock_user_to_remove.id = 101
    mock_user_to_remove.display_name = "User To Remove"
    mock_user_to_remove.username = "user_to_remove_uname"
    mock_user_to_remove.email = "remove@example.com"
    mock_user_to_remove.auth_method = "test_auth"
    mock_user_to_remove.profile_picture_url = None
    mock_user_to_remove.uuid = uuid.uuid4()
    mock_user_to_remove.is_admin = False

    # Configure _sa_instance_state for mock_user_to_remove.groups (backref)
    mock_user_to_remove_groups_collection = MagicMock(spec=list)
    mock_user_to_remove.groups = mock_user_to_remove_groups_collection
    mock_user_to_remove._sa_instance_state = MagicMock()
    mock_user_to_remove._sa_instance_state.manager.initialize_collection.return_value = (
        MagicMock(),
        mock_user_to_remove_groups_collection,
    )

    # Configure mock_group.users to be a MagicMock list that "contains" the user to be removed
    users_collection_on_group = MagicMock(spec=list)
    users_collection_on_group.__contains__.side_effect = (
        lambda item: item == mock_user_to_remove
    )
    mock_group.users = users_collection_on_group

    mock_user_query_results = {
        "user_to_remove_uname": mock_user_to_remove,
    }
    original_db_query = db.query

    def query_side_effect(model):
        if model.__name__ == "Group":
            mock_group_query = MagicMock()
            mock_group_query.filter.return_value.first.return_value = mock_group
            return mock_group_query
        elif model.__name__ == "User":
            mock_user_query = MagicMock()
            mock_user_query.filter.side_effect = lambda expr: MagicMock(
                first=MagicMock(
                    return_value=mock_user_query_results.get(expr.right.value)
                )
            )
            return mock_user_query
        return original_db_query(model)

    db.query.side_effect = query_side_effect

    db.commit.return_value = None
    db.refresh.return_value = None

    usernames_to_remove = ["user_to_remove_uname"]
    response = fastapi_test_client.request(
        "delete",
        f"/groups/{mock_group.name}/users",
        content=json.dumps(usernames_to_remove),
    )
    removed_users_response = response.json()

    assert response.status_code == 200
    assert len(removed_users_response) == 1
    assert removed_users_response[0]["username"] == "user_to_remove_uname"

    users_collection_on_group.remove.assert_called_once_with(mock_user_to_remove)
    assert db.commit.call_count == 1  # CRUD function commits once
    assert db.refresh.call_count == 1  # CRUD function refreshes once


def test_remove_users_from_group_group_not_found(fastapi_test_client, db):
    """Test the remove_users_from_group endpoint when group is not found."""
    db.query.return_value.filter.return_value.first.return_value = None

    usernames_to_remove = ["any_user"]
    response = fastapi_test_client.request(
        "delete",
        "/groups/NonExistentGroup/users",
        content=json.dumps(usernames_to_remove),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Group with name NonExistentGroup not found."}


def test_remove_users_from_group_user_not_in_group(
    fastapi_test_client, db, example_groups, mocker
):
    """Test removing a user that exists but is not in the specified group."""
    mock_group = example_groups[0]

    users_collection_mock = MagicMock(spec=list)
    # Explicitly mock the __contains__ method on the users_collection_mock
    users_collection_mock.__contains__ = MagicMock(
        return_value=False
    )  # User is NOT in the group
    mock_group.users = users_collection_mock

    mock_user_not_in_group = MagicMock(spec=UserSQLModel)
    mock_user_not_in_group.username = "user_not_in_group_uname"
    mock_user_not_in_group_groups_collection = MagicMock(spec=list)
    mock_user_not_in_group.groups = mock_user_not_in_group_groups_collection
    mock_user_not_in_group._sa_instance_state = MagicMock()
    mock_user_not_in_group._sa_instance_state.manager.initialize_collection.return_value = (
        MagicMock(),
        mock_user_not_in_group_groups_collection,
    )

    original_db_query = db.query

    def query_side_effect(model):
        if model.__name__ == "Group":
            return MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=mock_group))
                )
            )
        elif model.__name__ == "User":
            return MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(
                        first=MagicMock(return_value=mock_user_not_in_group)
                    )
                )
            )
        return original_db_query(model)

    db.query.side_effect = query_side_effect

    usernames_to_remove = ["user_not_in_group_uname"]
    response = fastapi_test_client.request(
        "delete",
        f"/groups/{mock_group.name}/users",
        content=json.dumps(usernames_to_remove),
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": f"User with username user_not_in_group_uname is not in group {mock_group.name}."
    }
    db.commit.assert_not_called()
    db.refresh.assert_not_called()


def test_delete_group(fastapi_test_client, db, example_groups):
    """Test the delete_group endpoint."""
    db.query.return_value.filter.return_value.first.return_value = example_groups[0]
    db.commit.return_value = None

    response = fastapi_test_client.delete("/groups/Group 1")
    assert response.status_code == 204  # Corrected status code
    db.commit.assert_called_once()
    db.query.return_value.filter.return_value.first.assert_called_once()


def test_delete_group_not_found(fastapi_test_client, db):
    """Test the delete_group endpoint when group is not found."""
    db.query.return_value.filter.return_value.first.return_value = None

    response = fastapi_test_client.delete("/groups/NonExistentGroup")
    assert response.status_code == 404
    assert response.json() == {"detail": "Group with name NonExistentGroup not found."}
