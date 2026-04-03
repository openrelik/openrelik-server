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

"""Tests for folder CRUD operations."""

import uuid
import pytest

from datastores.sql.crud.folder import (
    get_root_folders_from_db,
    get_subfolders_from_db,
    get_folder_from_db,
    create_root_folder_in_db,
    get_shared_folders_from_db,
    get_all_folders_from_db,
    create_subfolder_in_db,
    delete_folder_from_db,
)
from datastores.sql.models.folder import Folder
from datastores.sql.models.user import User
from api.v1 import schemas

def test_get_root_folders_from_db(db):
    """Test get_root_folders_from_db."""
    current_user = User(id=1)
    mock_query = db.query.return_value
    mock_join = mock_query.join.return_value
    mock_filter = mock_join.filter.return_value
    mock_order = mock_filter.order_by.return_value
    mock_order.all.return_value = [Folder(id=1, parent_id=None)]

    result = get_root_folders_from_db(db, current_user)

    db.query.assert_called_once_with(Folder)
    assert len(result) == 1
    assert result[0].id == 1

def test_get_subfolders_from_db(db):
    """Test get_subfolders_from_db."""
    parent_id = 1
    mock_query = db.query.return_value
    mock_filter = mock_query.filter_by.return_value
    mock_order = mock_filter.order_by.return_value
    mock_order.all.return_value = [Folder(id=2, parent_id=parent_id)]

    result = get_subfolders_from_db(db, parent_id)

    db.query.assert_called_once_with(Folder)
    mock_query.filter_by.assert_called_once_with(parent_id=parent_id)
    assert len(result) == 1
    assert result[0].id == 2

def test_get_folder_from_db(db):
    """Test get_folder_from_db."""
    folder_id = 1
    db.get.return_value = Folder(id=folder_id)

    result = get_folder_from_db(db, folder_id)

    db.get.assert_called_once_with(Folder, folder_id)
    assert result.id == folder_id

def test_create_root_folder_in_db(mocker, db):
    """Test create_root_folder_in_db."""
    mock_config = mocker.patch("datastores.sql.crud.folder.config")
    mock_os = mocker.patch("datastores.sql.crud.folder.os")
    
    current_user = User(id=1)
    new_folder = schemas.FolderCreateRequest(display_name="New Folder")
    
    mock_config.get.return_value.get.return_value.get.return_value = {"default": "default_provider"}
    mock_os.path.exists.return_value = False

    result = create_root_folder_in_db(db, new_folder, current_user)

    db.add.assert_called()
    db.commit.assert_called()
    db.refresh.assert_called()
    mock_os.mkdir.assert_called_once()
    assert result.display_name == "New Folder"

def test_get_shared_folders_from_db(mocker, db):
    """Test get_shared_folders_from_db."""
    current_user = User(id=1)
    
    mock_q = mocker.MagicMock()
    db.query.return_value = mock_q
    mock_q.join.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.union.return_value = mock_q
    mock_q.select_from.return_value = mock_q
    mock_q.outerjoin.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    
    mock_q.all.return_value = [Folder(id=2)]
    
    result = get_shared_folders_from_db(db, current_user)
    
    assert len(result) == 1
    assert result[0].id == 2

def test_get_all_folders_from_db_default(mocker, db):
    """Test get_all_folders_from_db in default mode (no search)."""
    current_user = User(id=1)
    
    mock_q = mocker.MagicMock()
    db.query.return_value = mock_q
    mock_q.join.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.union.return_value = mock_q
    mock_q.select_from.return_value = mock_q
    mock_q.outerjoin.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.distinct.return_value = mock_q
    mock_q.offset.return_value = mock_q
    mock_q.limit.return_value = mock_q
    
    mock_q.all.return_value = [Folder(id=1), Folder(id=2)]
    mock_q.count.return_value = 2
    
    folders, total = get_all_folders_from_db(db, current_user)
    
    assert len(folders) == 2
    assert total == 2

def test_get_all_folders_from_db_search(mocker, db):
    """Test get_all_folders_from_db in search mode."""
    mock_aliased = mocker.patch("datastores.sql.crud.folder.aliased")
    mock_select = mocker.patch("datastores.sql.crud.folder.select")
    mock_union = mocker.patch("datastores.sql.crud.folder.union")
    
    current_user = User(id=1)
    
    # Mock the complex select/union CTE generation
    mock_stmt = mocker.MagicMock()
    mock_select.return_value = mock_stmt
    mock_stmt.join.return_value = mock_stmt
    mock_stmt.filter.return_value = mock_stmt
    mock_stmt.cte.return_value = mocker.MagicMock()
    
    # Mock aliased to return a mock that has .c.id
    mock_cte_alias = mocker.MagicMock()
    mock_aliased.return_value = mock_cte_alias
    
    # Use the fluent mock trick
    mock_q = mocker.MagicMock()
    db.query.return_value = mock_q
    mock_q.join.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.union.return_value = mock_q
    mock_q.select_from.return_value = mock_q
    mock_q.outerjoin.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.distinct.return_value = mock_q
    mock_q.offset.return_value = mock_q
    mock_q.limit.return_value = mock_q
    
    mock_q.all.return_value = [Folder(id=1)]
    mock_q.count.return_value = 1
    mock_q.scalar.return_value = 1 # For total count in search mode
    
    folders, total = get_all_folders_from_db(db, current_user, search_term="test")
    
    assert len(folders) == 1
    assert total == 1

def test_create_subfolder_in_db(mocker, db):
    """Test create_subfolder_in_db."""
    mock_config = mocker.patch("datastores.sql.crud.folder.config")
    mock_get_folder = mocker.patch("datastores.sql.crud.folder.get_folder_from_db")
    mock_os = mocker.patch("datastores.sql.crud.folder.os")
    
    current_user = User(id=1)
    parent_folder = Folder(id=1, uuid=uuid.uuid4())
    mock_get_folder.return_value = parent_folder
    
    new_folder = schemas.FolderCreateRequest(display_name="Subfolder")
    
    mock_config.get.return_value.get.return_value.get.return_value = {"default": "default_provider"}
    mock_os.path.exists.return_value = False
    
    result = create_subfolder_in_db(db, folder_id=1, new_folder=new_folder, current_user=current_user)
    
    db.add.assert_called()
    db.commit.assert_called()
    mock_os.mkdir.assert_called_once()
    assert result.display_name == "Subfolder"

def test_delete_folder_from_db(db):
    """Test delete_folder_from_db."""
    folder_id = 1
    
    mock_execute = db.execute.return_value
    mock_scalars = mock_execute.scalars.return_value
    mock_scalars.all.return_value = [1, 2, 3] # Folder IDs
    
    delete_folder_from_db(db, folder_id)
    
    assert db.execute.call_count == 3
    db.commit.assert_called_once()

def test_delete_folder_from_db_empty(db):
    """Test delete_folder_from_db when no folders found."""
    folder_id = 1
    
    mock_execute = db.execute.return_value
    mock_scalars = mock_execute.scalars.return_value
    mock_scalars.all.return_value = []
    
    delete_folder_from_db(db, folder_id)
    
    assert db.execute.call_count == 1
    db.commit.assert_not_called()
