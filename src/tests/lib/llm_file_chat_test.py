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

from lib.llm_file_chat import create_chat_session

def test_create_chat_session(mocker, db):
    """Test create_chat_session successfully creates a session."""
    mocker.patch("lib.llm_file_chat.database.SessionLocal", return_value=db)
    mock_get_file = mocker.patch("lib.llm_file_chat.get_file_from_db")
    mock_llm_manager = mocker.patch("lib.llm_file_chat.manager.LLMManager")
    
    mock_file = mocker.MagicMock()
    mock_file.path = "/dummy/path"
    mock_file.magic_text = "text/plain"
    mock_file.display_name = "test.txt"
    mock_file.summaries = [mocker.MagicMock(summary="Test summary")]
    mock_get_file.return_value = mock_file
    
    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    mock_llm = mocker.MagicMock()
    mock_provider.return_value = mock_llm
    
    file_content = "Hello, world!"
    m = mocker.mock_open(read_data=file_content)
    mocker.patch("builtins.open", m)
    
    llm = create_chat_session("google", "gemini-pro", file_id=1)
        
    mock_get_file.assert_called_once_with(db, 1)
    mock_llm_manager.return_value.get_provider.assert_called_once_with("google")
    mock_provider.assert_called_once()
    
    # Check if system instructions contain expected content
    kwargs = mock_provider.call_args.kwargs
    assert "Hello, world!" in kwargs["system_instructions"]
    assert "test.txt" in kwargs["system_instructions"]
    assert "Test summary" in kwargs["system_instructions"]
    
    assert llm == mock_llm

def test_create_chat_session_encoding_fallback(mocker, db):
    """Test create_chat_session falls back to different encodings."""
    mocker.patch("lib.llm_file_chat.database.SessionLocal", return_value=db)
    mocker.patch("lib.llm_file_chat.get_file_from_db")
    mock_llm_manager = mocker.patch("lib.llm_file_chat.manager.LLMManager")
    
    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    
    # Mock open call itself to raise exception for the first call
    # and return a working mock for the second.
    
    mock_file_handle_fail = mocker.MagicMock()
    mock_file_handle_fail.__enter__.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "")
    
    mock_file_handle_success = mocker.MagicMock()
    mock_file_handle_success.__enter__.return_value.read.return_value = "ISO content"
    
    mock_open_func = mocker.patch("builtins.open")
    mock_open_func.side_effect = [mock_file_handle_fail, mock_file_handle_success]
        
    create_chat_session("google", "gemini-pro", file_id=1)
        
    assert mock_open_func.call_count == 2

def test_create_chat_session_no_summary(mocker, db):
    """Test create_chat_session when file has no summary."""
    mocker.patch("lib.llm_file_chat.database.SessionLocal", return_value=db)
    mock_get_file = mocker.patch("lib.llm_file_chat.get_file_from_db")
    mock_llm_manager = mocker.patch("lib.llm_file_chat.manager.LLMManager")
    
    mock_file = mocker.MagicMock()
    mock_file.path = "/dummy/path"
    mock_file.summaries = []
    mock_get_file.return_value = mock_file
    
    mock_provider = mocker.MagicMock()
    mock_llm_manager.return_value.get_provider.return_value = mock_provider
    
    m = mocker.mock_open(read_data="content")
    mocker.patch("builtins.open", m)
    
    create_chat_session("google", "gemini-pro", file_id=1)
        
    kwargs = mock_provider.call_args.kwargs
    assert "No summary available" in kwargs["system_instructions"]
