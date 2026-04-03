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

"""Tests for file CRUD operations."""

import os
import uuid
import pytest

from datastores.sql.crud.file import (
    get_files_from_db,
    get_file_from_db,
    get_file_by_uuid_from_db,
    create_file_in_db,
    delete_file_from_db,
    get_file_summary_from_db,
    create_file_summary_in_db,
    update_file_summary_in_db,
    create_file_report_in_db,
    create_file_chat_in_db,
    create_file_chat_message_in_db,
    get_latest_file_chat_from_db,
)
from datastores.sql.models.file import File, FileSummary, FileReport, FileChat, FileChatMessage
from datastores.sql.models.user import UserRole

def test_get_files_from_db(db):
    """Test get_files_from_db."""
    folder_id = 1
    mock_query = db.query.return_value
    mock_filter = mock_query.filter_by.return_value
    mock_order = mock_filter.order_by.return_value
    mock_order.all.return_value = [File(id=1, folder_id=folder_id)]

    result = get_files_from_db(db, folder_id)

    db.query.assert_called_once_with(File)
    mock_query.filter_by.assert_called_once_with(folder_id=folder_id)
    assert len(result) == 1
    assert result[0].id == 1

def test_get_file_from_db(db):
    """Test get_file_from_db."""
    file_id = 1
    db.get.return_value = File(id=file_id)

    result = get_file_from_db(db, file_id)

    db.get.assert_called_once_with(File, file_id)
    assert result.id == file_id

def test_get_file_by_uuid_from_db(db):
    """Test get_file_by_uuid_from_db."""
    uuid_str = str(uuid.uuid4())
    mock_query = db.query.return_value
    mock_filter = mock_query.filter_by.return_value
    mock_filter.first.return_value = File(id=1, uuid=uuid.UUID(uuid_str))

    result = get_file_by_uuid_from_db(db, uuid_str)

    db.query.assert_called_once_with(File)
    mock_query.filter_by.assert_called_once_with(uuid=uuid.UUID(uuid_str))
    assert result.uuid == uuid.UUID(uuid_str)

def test_delete_file_from_db(mocker, db):
    """Test delete_file_from_db."""
    file_id = 1
    mock_file = mocker.MagicMock()
    db.get.return_value = mock_file

    delete_file_from_db(db, file_id)

    db.get.assert_called_once_with(File, file_id)
    mock_file.soft_delete.assert_called_once()
    db.commit.assert_called_once()

def test_create_file_in_db(mocker, db):
    """Test create_file_in_db."""
    mock_get_folder = mocker.patch("datastores.sql.crud.file.get_folder_from_db")
    mock_magic = mocker.patch("datastores.sql.crud.file.magic.from_file")
    mock_stat = mocker.patch("datastores.sql.crud.file.os.stat")
    mock_file_cls = mocker.patch("datastores.sql.crud.file.File")
    mock_user_role = mocker.patch("datastores.sql.crud.file.UserRole")

    mock_folder = mocker.MagicMock()
    mock_folder.path = "dummy_folder_path"
    mock_get_folder.return_value = mock_folder
    
    mock_magic.side_effect = ["plain text", "text/plain"]
    mock_stat.return_value.st_size = 100
    
    mock_file_create = mocker.MagicMock()
    mock_file_create.folder_id = 1
    mock_file_create.uuid = uuid.uuid4()
    mock_file_create.extension = "txt"
    mock_file_create.data_type = None
    mock_file_create.model_dump.return_value = {"folder_id": 1}
    
    mock_current_user = mocker.MagicMock()
    
    mock_file_instance = mocker.MagicMock()
    mock_file_cls.return_value = mock_file_instance
    
    mock_user_role_instance = mocker.MagicMock()
    mock_user_role.return_value = mock_user_role_instance
    
    result = create_file_in_db(db, mock_file_create, mock_current_user)
    
    mock_file_cls.assert_called_once()
    db.add.assert_any_call(mock_file_instance)
    db.add.assert_any_call(mock_user_role_instance)
    assert result == mock_file_instance

def test_get_file_summary_from_db(db):
    """Test get_file_summary_from_db."""
    summary_id = 1
    db.get.return_value = FileSummary(id=summary_id)
    
    result = get_file_summary_from_db(db, summary_id)
    
    db.get.assert_called_once_with(FileSummary, summary_id)
    assert result.id == summary_id

def test_create_file_summary_in_db(mocker, db):
    """Test create_file_summary_in_db."""
    mock_file_summary_cls = mocker.patch("datastores.sql.crud.file.FileSummary")
    
    mock_summary_create = mocker.MagicMock()
    mock_summary_create.model_dump.return_value = {"summary": "test"}
    
    mock_summary_instance = mocker.MagicMock()
    mock_file_summary_cls.return_value = mock_summary_instance
    
    result = create_file_summary_in_db(db, mock_summary_create)
    
    mock_file_summary_cls.assert_called_once_with(summary="test")
    db.add.assert_called_once_with(mock_summary_instance)
    db.commit.assert_called_once()
    assert result == mock_summary_instance

def test_update_file_summary_in_db(mocker, db):
    """Test update_file_summary_in_db."""
    mock_summary = mocker.MagicMock()
    
    result = update_file_summary_in_db(db, mock_summary)
    
    db.add.assert_called_once_with(mock_summary)
    db.commit.assert_called_once()
    assert result == mock_summary

def test_create_file_report_in_db(mocker, db):
    """Test create_file_report_in_db."""
    mock_get_file = mocker.patch("datastores.sql.crud.file.get_file_by_uuid_from_db")
    mock_file_report_cls = mocker.patch("datastores.sql.crud.file.FileReport")
    
    mock_report_create = mocker.MagicMock()
    mock_report_create.input_file_uuid = "uuid1"
    mock_report_create.content_file_uuid = "uuid2"
    mock_report_create.summary = "summary"
    mock_report_create.priority = "high"
    
    mock_input_file = mocker.MagicMock()
    mock_content_file = mocker.MagicMock()
    mock_content_file.path = "dummy_path"
    
    mock_get_file.side_effect = [mock_input_file, mock_content_file]
    
    mock_report_instance = mocker.MagicMock()
    mock_file_report_cls.return_value = mock_report_instance
    
    m = mocker.mock_open(read_data="report content")
    mocker.patch("builtins.open", m)
    
    result = create_file_report_in_db(db, mock_report_create, 1)
        
    mock_file_report_cls.assert_called_once_with(
        summary="summary",
        priority="high",
        markdown="report content",
        file=mock_input_file,
        content_file=mock_content_file,
        task_id=1
    )
    db.add.assert_called_once_with(mock_report_instance)
    db.commit.assert_called_once()
    assert result == mock_report_instance

def test_create_file_chat_in_db(mocker, db):
    """Test create_file_chat_in_db."""
    mock_file_chat_cls = mocker.patch("datastores.sql.crud.file.FileChat")
    
    mock_chat_create = mocker.MagicMock()
    mock_chat_create.model_dump.return_value = {"file_id": 1}
    
    mock_chat_instance = mocker.MagicMock()
    mock_file_chat_cls.return_value = mock_chat_instance
    
    result = create_file_chat_in_db(db, mock_chat_create)
    
    mock_file_chat_cls.assert_called_once_with(file_id=1)
    db.add.assert_called_once_with(mock_chat_instance)
    db.commit.assert_called_once()
    assert result == mock_chat_instance

def test_create_file_chat_message_in_db(mocker, db):
    """Test create_file_chat_message_in_db."""
    mock_file_chat_message_cls = mocker.patch("datastores.sql.crud.file.FileChatMessage")
    
    mock_msg_create = mocker.MagicMock()
    mock_msg_create.model_dump.return_value = {"chat_id": 1}
    
    mock_msg_instance = mocker.MagicMock()
    mock_file_chat_message_cls.return_value = mock_msg_instance
    
    result = create_file_chat_message_in_db(db, mock_msg_create)
    
    mock_file_chat_message_cls.assert_called_once_with(chat_id=1)
    db.add.assert_called_once_with(mock_msg_instance)
    db.commit.assert_called_once()
    assert result == mock_msg_instance

def test_get_latest_file_chat_from_db(db):
    """Test get_latest_file_chat_from_db."""
    mock_query = db.query.return_value
    mock_filter = mock_query.filter_by.return_value
    mock_order = mock_filter.order_by.return_value
    mock_order.first.return_value = FileChat(id=1)
    
    result = get_latest_file_chat_from_db(db, 1, 1)
    
    db.query.assert_called_once_with(FileChat)
    mock_query.filter_by.assert_called_once_with(file_id=1, user_id=1)
    assert result.id == 1
