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

"""Tests for user CRUD operations."""

import uuid
import pytest

from datastores.sql.crud.user import (
    get_users_from_db,
    get_user_from_db,
    create_user_in_db,
    search_users,
)
from datastores.sql.models.user import User
from api.v1 import schemas

def test_get_users_from_db(db):
    """Test get_users_from_db."""
    mock_query = db.query.return_value
    mock_query.all.return_value = [User(id=1)]

    result = get_users_from_db(db)

    db.query.assert_called_once_with(User)
    assert len(result) == 1
    assert result[0].id == 1

def test_get_user_from_db(db):
    """Test get_user_from_db."""
    user_id = 1
    mock_query = db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = User(id=user_id)

    result = get_user_from_db(db, user_id)

    db.query.assert_called_once_with(User)
    # filter condition is User.id == user_id, which is an expression.
    # We can't easily assert the exact expression object, but we can assert filter was called.
    mock_query.filter.assert_called_once()
    assert result.id == user_id

def test_create_user_in_db(mocker, db):
    """Test create_user_in_db."""
    mock_get_group = mocker.patch("datastores.sql.crud.user.get_group_by_name_from_db")
    new_user = schemas.UserCreate(
        username="testuser",
        display_name="Test User",
        email="test@example.com",
        password_hash="hash",
        password_hash_algorithm="argon2id",
        auth_method="local",
        uuid=uuid.uuid4(),
    )
    
    # Mock "Everyone" group
    mock_group = mocker.MagicMock()
    mock_get_group.return_value = mock_group

    result = create_user_in_db(db, new_user)

    db.add.assert_called()
    db.commit.assert_called()
    db.refresh.assert_called()
    assert result.username == "testuser"
    assert mock_group in result.groups

def test_search_users(db):
    """Test search_users."""
    search_str = "test"
    mock_query = db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.all.return_value = [User(username="testuser")]

    result = search_users(db, search_str)

    db.query.assert_called_once_with(User)
    mock_query.filter.assert_called_once()
    assert len(result) == 1
    assert result[0].username == "testuser"
