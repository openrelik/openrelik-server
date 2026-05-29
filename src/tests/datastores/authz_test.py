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
from fastapi import HTTPException
from unittest.mock import MagicMock

from datastores.sql.crud.authz import (
    check_user_access,
    require_access,
    raise_authorization_error,
    AuthorizationError
)
from datastores.sql.models.file import File
from datastores.sql.models.folder import Folder
from datastores.sql.models.user import User, UserRole
from datastores.sql.models.group import Group, GroupRole
from datastores.sql.models.role import Role


def test_raise_authorization_error():
    with pytest.raises(HTTPException) as exc_info:
        raise_authorization_error(True, "Access Denied")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Access Denied"

    with pytest.raises(AuthorizationError) as exc_info:
        raise_authorization_error(False, "Access Denied")
    assert exc_info.value.message == "Access Denied"


def test_check_user_access_invalid_args():
    db = MagicMock()
    user = User(id=1)
    
    with pytest.raises(ValueError, match="Database session \\(db\\) cannot be None."):
        check_user_access(None, user, [Role.VIEWER])

    with pytest.raises(ValueError, match="User object cannot be None."):
        check_user_access(db, None, [Role.VIEWER])

    with pytest.raises(ValueError, match="Either folder or file must be provided."):
        check_user_access(db, user, [Role.VIEWER])


def test_check_user_access_file_direct_role(db):
    user = User(id=1, groups=[])
    file = File(id=1, folder=Folder(id=1))
    
    # Mockdb query for UserRole file
    mock_query = db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = UserRole(user_id=1, file_id=1, role=Role.VIEWER)
    
    result = check_user_access(db, user, [Role.VIEWER], file=file)
    assert result is not False
    assert result.role == Role.VIEWER


def test_check_user_access_file_group_role(db):
    group = Group(id=1)
    user = User(id=1, groups=[group])
    file = File(id=1, folder=Folder(id=1))
    
    # UserRole first() returns None, then GroupRole returns role
    mock_query = db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.side_effect = [None, GroupRole(group_id=1, file_id=1, role=Role.EDITOR)]
    
    result = check_user_access(db, user, [Role.VIEWER, Role.EDITOR], file=file)
    assert result is not False
    assert result.role == Role.EDITOR

def test_check_user_access_file_fallback_to_folder(db):
    user = User(id=1, groups=[])
    folder = Folder(id=1, parent=None)
    file = File(id=1, folder=folder)
    
    # 1. UserRole for file returns None
    # 2. GroupRole for file (no groups) -> skips
    # 3. UserRole for folder returns Reader
    mock_query = db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.side_effect = [None, UserRole(user_id=1, folder_id=1, role=Role.VIEWER)]
    
    result = check_user_access(db, user, [Role.VIEWER], file=file)
    assert result is not False
    assert result.role == Role.VIEWER

def test_check_user_access_folder_no_access(db):
    user = User(id=1, groups=[])
    folder = Folder(id=1, parent=None)
    
    mock_query = db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = UserRole(user_id=1, folder_id=1, role=Role.NO_ACCESS)
    
    result = check_user_access(db, user, [Role.VIEWER], folder=folder)
    assert result is False

def test_check_user_access_folder_group_role(db):
    group = Group(id=1)
    user = User(id=1, groups=[group])
    folder = Folder(id=1, parent=None)
    
    mock_query = db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.side_effect = [None, GroupRole(group_id=1, folder_id=1, role=Role.OWNER)]
    
    result = check_user_access(db, user, [Role.OWNER], folder=folder)
    assert result is not False
    assert result.role == Role.OWNER

def test_check_user_access_folder_no_access_found(db):
    user = User(id=1, groups=[])
    folder = Folder(id=1, parent=None)
    
    mock_query = db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.side_effect = None
    mock_filter.first.return_value = None
    
    result = check_user_access(db, user, [Role.OWNER], folder=folder)
    assert result is False


@pytest.mark.asyncio
async def test_require_access_decorator_async(db, authz):
    @require_access([Role.VIEWER])
    async def dummy_endpoint(db, folder_id, current_user):
        return True

    user = User(id=1, groups=[])
    folder = Folder(id=1)
    db.get.return_value = folder
    
    result = await dummy_endpoint(db=db, folder_id=1, current_user=user)
    assert result is True


def test_require_access_decorator_sync(db, authz):
    @require_access([Role.VIEWER])
    def dummy_endpoint(db, folder_id, current_user):
        return True

    user = User(id=1, groups=[])
    folder = Folder(id=1)
    db.get.return_value = folder
    
    result = dummy_endpoint(db=db, folder_id=1, current_user=user)
    assert result is True

def test_require_access_decorator_folder_not_found(db, authz):
    @require_access([Role.VIEWER])
    def dummy_endpoint(db, folder_id, current_user):
        return True

    user = User(id=1, groups=[])
    db.get.return_value = None
    
    with pytest.raises(HTTPException) as exc_info:
        dummy_endpoint(db=db, folder_id=1, current_user=user)
    assert exc_info.value.status_code == 404

def test_require_access_decorator_file_not_found(db, authz):
    @require_access([Role.VIEWER])
    def dummy_endpoint(db, file_id, current_user):
        return True

    user = User(id=1, groups=[])
    db.get.return_value = None
    
    with pytest.raises(HTTPException) as exc_info:
        dummy_endpoint(db=db, file_id=1, current_user=user)
    assert exc_info.value.status_code == 404

def test_require_access_decorator_access_denied(db, authz):
    authz.return_value = False
    @require_access([Role.VIEWER])
    def dummy_endpoint(db, file_id, current_user):
        return True

    user = User(id=1, groups=[])
    file = File(id=1, folder=Folder(id=1))
    db.get.return_value = file
    
    with pytest.raises(HTTPException) as exc_info:
        dummy_endpoint(db=db, file_id=1, current_user=user)
    assert exc_info.value.status_code == 403
