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

from lib.llm_summary import generate_summary, generate_sql_summary


def test_generate_summary_success(mocker, db):
    """Test generate_summary success path."""
    mocker.patch("lib.llm_summary.database.SessionLocal", return_value=db)
    mock_llm_manager = mocker.patch("lib.llm_summary.manager.LLMManager")
    mock_get_file = mocker.patch("lib.llm_summary.get_file_from_db")
    mock_get_summary = mocker.patch("lib.llm_summary.get_file_summary_from_db")
    mock_update_summary = mocker.patch("lib.llm_summary.update_file_summary_in_db")

    # Mock LLM
    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    mock_llm = mocker.MagicMock()
    mock_provider.return_value = mock_llm
    mock_llm.generate_file_analysis.return_value = "analysis details"
    mock_llm.generate.return_value = "summary with http link"
    mock_llm.DISPLAY_NAME = "MockLLM"
    mock_llm.config = {"model": "mock-model"}

    mock_file = mocker.MagicMock()
    mock_file.path = "dummy_path"
    mock_file.magic_text = "text"
    mock_file.display_name = "file.txt"
    mock_get_file.return_value = mock_file

    mock_file_summary = mocker.MagicMock()
    mock_get_summary.return_value = mock_file_summary

    # Mock open
    m = mocker.mock_open(read_data="file content")
    mocker.patch("builtins.open", m)

    generate_summary("google", "gemini-pro", 1, 1)

    mock_update_summary.assert_called_once()
    assert mock_file_summary.summary == "summary with hXXp link"
    assert mock_file_summary.status_short == "complete"


def test_generate_summary_unicode_error(mocker, db):
    """Test generate_summary handling UnicodeDecodeError."""
    mocker.patch("lib.llm_summary.database.SessionLocal", return_value=db)
    mock_llm_manager = mocker.patch("lib.llm_summary.manager.LLMManager")
    mock_get_file = mocker.patch("lib.llm_summary.get_file_from_db")
    mock_get_summary = mocker.patch("lib.llm_summary.get_file_summary_from_db")
    mock_update_summary = mocker.patch("lib.llm_summary.update_file_summary_in_db")

    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    mock_llm = mocker.MagicMock()
    mock_provider.return_value = mock_llm
    mock_llm.generate_file_analysis.return_value = "analysis details"
    mock_llm.generate.return_value = "summary"
    mock_llm.DISPLAY_NAME = "MockLLM"
    mock_llm.config = {"model": "mock-model"}

    mock_file = mocker.MagicMock()
    mock_file.path = "dummy_path"
    mock_get_file.return_value = mock_file

    mock_file_summary = mocker.MagicMock()
    mock_get_summary.return_value = mock_file_summary

    # Mock open to fail on utf-8, succeed on utf-16
    m = mocker.mock_open()
    m.side_effect = [
        UnicodeDecodeError("utf-8", b"", 0, 1, "reason"),
        mocker.mock_open(read_data="content").return_value,
    ]

    mocker.patch("builtins.open", m)

    generate_summary("google", "gemini-pro", 1, 1)

    assert mock_update_summary.called


def test_generate_summary_llm_exception(mocker, db):
    """Test generate_summary handling LLM exceptions."""
    mocker.patch("lib.llm_summary.database.SessionLocal", return_value=db)
    mock_llm_manager = mocker.patch("lib.llm_summary.manager.LLMManager")
    mock_get_file = mocker.patch("lib.llm_summary.get_file_from_db")
    mock_get_summary = mocker.patch("lib.llm_summary.get_file_summary_from_db")

    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    mock_llm = mocker.MagicMock()
    mock_provider.return_value = mock_llm

    mock_file = mocker.MagicMock()
    mock_file.path = "dummy_path"
    mock_get_file.return_value = mock_file

    mock_file_summary = mocker.MagicMock()
    mock_get_summary.return_value = mock_file_summary

    mock_llm.generate_file_analysis.side_effect = Exception("LLM Error")

    m = mocker.mock_open(read_data="file content")
    mocker.patch("builtins.open", m)

    generate_summary("google", "gemini-pro", 1, 1)

    assert "LLM Error" in mock_file_summary.summary


def test_generate_sql_summary_success(mocker, db):
    """Test generate_sql_summary success path."""
    mocker.patch("lib.llm_summary.database.SessionLocal", return_value=db)
    mock_llm_manager = mocker.patch("lib.llm_summary.manager.LLMManager")
    mock_get_file = mocker.patch("lib.llm_summary.get_file_from_db")
    mock_get_summary = mocker.patch("lib.llm_summary.get_file_summary_from_db")
    mock_update_summary = mocker.patch("lib.llm_summary.update_file_summary_in_db")
    mock_get_schemas = mocker.patch("lib.llm_summary.duckdb_utils.get_tables_schemas")
    mock_run_query = mocker.patch("lib.llm_summary.duckdb_utils.run_query")

    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    mock_llm = mocker.MagicMock()
    mock_provider.return_value = mock_llm
    mock_llm.generate.return_value = "sql summary"
    mock_llm.DISPLAY_NAME = "MockLLM"
    mock_llm.config = {"model": "mock-model"}

    mock_file = mocker.MagicMock()
    mock_get_file.return_value = mock_file

    mock_file_summary = mocker.MagicMock()
    mock_get_summary.return_value = mock_file_summary

    mock_get_schemas.return_value = {"table1": {"col1": "TEXT"}}
    mock_run_query.return_value = [{"col1": "val1"}]

    generate_sql_summary("google", "gemini-pro", 1, 1)

    mock_update_summary.assert_called_once()
    assert mock_file_summary.summary == "sql summary"


def test_generate_sql_summary_query_error(mocker, db):
    """Test generate_sql_summary handling query errors."""
    mocker.patch("lib.llm_summary.database.SessionLocal", return_value=db)
    mock_llm_manager = mocker.patch("lib.llm_summary.manager.LLMManager")
    mock_get_file = mocker.patch("lib.llm_summary.get_file_from_db")
    mock_get_summary = mocker.patch("lib.llm_summary.get_file_summary_from_db")
    mock_update_summary = mocker.patch("lib.llm_summary.update_file_summary_in_db")
    mock_get_schemas = mocker.patch("lib.llm_summary.duckdb_utils.get_tables_schemas")
    mock_run_query = mocker.patch("lib.llm_summary.duckdb_utils.run_query")

    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    mock_llm = mocker.MagicMock()
    mock_provider.return_value = mock_llm
    mock_llm.generate.return_value = "sql summary"
    mock_llm.DISPLAY_NAME = "MockLLM"
    mock_llm.config = {"model": "mock-model"}

    mock_file = mocker.MagicMock()
    mock_get_file.return_value = mock_file

    mock_file_summary = mocker.MagicMock()
    mock_get_summary.return_value = mock_file_summary

    mock_get_schemas.return_value = {"table1": {"col1": "TEXT"}}
    # Simulate query error
    mock_run_query.side_effect = Exception("Query error")

    generate_sql_summary("google", "gemini-pro", 1, 1)

    # It should still succeed and call generate with empty sample data for that table
    mock_llm.generate.assert_called_once()
    mock_update_summary.assert_called_once()


def test_generate_sql_summary_llm_exception(mocker, db):
    """Test generate_sql_summary handling LLM exceptions."""
    mocker.patch("lib.llm_summary.database.SessionLocal", return_value=db)
    mock_llm_manager = mocker.patch("lib.llm_summary.manager.LLMManager")
    mock_get_file = mocker.patch("lib.llm_summary.get_file_from_db")
    mock_get_summary = mocker.patch("lib.llm_summary.get_file_summary_from_db")
    mock_get_schemas = mocker.patch("lib.llm_summary.duckdb_utils.get_tables_schemas")
    mock_run_query = mocker.patch("lib.llm_summary.duckdb_utils.run_query")

    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    mock_llm = mocker.MagicMock()
    mock_provider.return_value = mock_llm

    mock_file = mocker.MagicMock()
    mock_get_file.return_value = mock_file

    mock_file_summary = mocker.MagicMock()
    mock_get_summary.return_value = mock_file_summary

    mock_get_schemas.return_value = {"table1": {"col1": "TEXT"}}
    mock_run_query.return_value = [{"col1": "val1"}]

    mock_llm.generate.side_effect = Exception("LLM Error")

    generate_sql_summary("google", "gemini-pro", 1, 1)

    assert "LLM Error" in mock_file_summary.summary
