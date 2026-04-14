# Copyright 2025 Google LLC
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
from lib.duckdb_utils import (
    is_sql_file,
    _duckdb_sqlite_connection,
    get_tables_schemas,
    run_query,
    generate_sql_query,
)


def test_is_sql_file():
    """Test is_sql_file with various inputs."""
    assert is_sql_file("SQLite 3.x database") is True
    assert is_sql_file("DuckDB database") is True
    assert is_sql_file("Some other database") is False
    assert is_sql_file("Just some text") is False
    assert is_sql_file("") is False
    assert is_sql_file(None) is False


def test_duckdb_sqlite_connection(mocker):
    """Test _duckdb_sqlite_connection when extension does not exist."""
    mock_conn = mocker.MagicMock()
    mock_connect = mocker.patch(
        "lib.duckdb_utils.duckdb.connect", return_value=mock_conn
    )
    mock_exists = mocker.patch("lib.duckdb_utils.os.path.exists", return_value=False)

    with _duckdb_sqlite_connection("dummy_path") as conn:
        assert conn == mock_conn

    mock_conn.execute.assert_any_call("INSTALL sqlite; LOAD sqlite;")
    mock_conn.execute.assert_any_call("SET enable_external_access = false;")
    mock_conn.execute.assert_any_call(
        "ATTACH 'dummy_path' AS sqlite_db (TYPE SQLITE, READ_ONLY TRUE);"
    )
    mock_conn.execute.assert_any_call("USE sqlite_db;")
    mock_conn.close.assert_called_once()


def test_duckdb_sqlite_connection_with_ext(mocker):
    """Test _duckdb_sqlite_connection when extension exists."""
    mock_conn = mocker.MagicMock()
    mocker.patch("lib.duckdb_utils.duckdb.connect", return_value=mock_conn)
    mocker.patch("lib.duckdb_utils.os.path.exists", return_value=True)

    with _duckdb_sqlite_connection("dummy_path") as conn:
        assert conn == mock_conn

    mock_conn.execute.assert_any_call(
        "INSTALL '/app/openrelik/sqlite_scanner.duckdb_extension'; LOAD '/app/openrelik/sqlite_scanner.duckdb_extension';"
    )


def test_get_tables_schemas(mocker):
    """Test get_tables_schemas success path."""
    mocker.patch("lib.duckdb_utils.is_sql_file", return_value=True)
    mock_conn = mocker.MagicMock()
    mocker.patch(
        "lib.duckdb_utils._duckdb_sqlite_connection"
    ).return_value.__enter__.return_value = mock_conn

    mock_file = mocker.MagicMock()
    mock_file.magic_text = "SQLite database"
    mock_file.path = "dummy_path"

    # Mock tables query
    mock_conn.execute.return_value.fetchall.side_effect = [
        [("table1",), ("table2",)],  # Tables list
        [(0, "col1", "TEXT"), (1, "col2", "INT")],  # table1 info
        [(0, "col3", "BLOB")],  # table2 info
    ]

    result = get_tables_schemas(mock_file)

    assert result == {
        "table1": {"col1": "TEXT", "col2": "INT"},
        "table2": {"col3": "BLOB"},
    }


def test_get_tables_schemas_invalid_file(mocker):
    """Test get_tables_schemas with invalid file."""
    mocker.patch("lib.duckdb_utils.is_sql_file", return_value=False)
    mock_file = mocker.MagicMock()
    mock_file.magic_text = "text"

    result = get_tables_schemas(mock_file)

    assert result == {}


def test_get_tables_schemas_exception(mocker):
    """Test get_tables_schemas raises RuntimeError on exception."""
    mocker.patch("lib.duckdb_utils.is_sql_file", return_value=True)
    mock_conn = mocker.MagicMock()
    mocker.patch(
        "lib.duckdb_utils._duckdb_sqlite_connection"
    ).return_value.__enter__.return_value = mock_conn
    mock_file = mocker.MagicMock()
    mock_file.magic_text = "SQLite database"

    mock_conn.execute.side_effect = Exception("DB Error")

    with pytest.raises(RuntimeError, match="DB Error"):
        get_tables_schemas(mock_file)


def test_run_query(mocker):
    """Test run_query success path."""
    mocker.patch("lib.duckdb_utils.is_sql_file", return_value=True)
    mock_conn = mocker.MagicMock()
    mocker.patch(
        "lib.duckdb_utils._duckdb_sqlite_connection"
    ).return_value.__enter__.return_value = mock_conn

    mock_file = mocker.MagicMock()
    mock_file.magic_text = "SQLite database"
    mock_file.path = "dummy_path"

    mock_cursor = mocker.MagicMock()
    mock_cursor.description = [("col1",), ("col2",)]
    mock_cursor.fetchall.return_value = [("val1", 2), (b"val2", 3)]
    mock_conn.execute.return_value = mock_cursor

    result = run_query(mock_file, "SELECT * FROM foo")

    assert result == [{"col1": "val1", "col2": 2}, {"col1": "b'val2'", "col2": 3}]


def test_run_query_invalid_file(mocker):
    """Test run_query raises RuntimeError on invalid file."""
    mocker.patch("lib.duckdb_utils.is_sql_file", return_value=False)
    mock_file = mocker.MagicMock()
    mock_file.magic_text = "text"

    with pytest.raises(RuntimeError, match="File is not a supported SQL format"):
        run_query(mock_file, "SELECT * FROM foo")


def test_run_query_exception(mocker):
    """Test run_query raises RuntimeError on exception."""
    mocker.patch("lib.duckdb_utils.is_sql_file", return_value=True)
    mock_conn = mocker.MagicMock()
    mocker.patch(
        "lib.duckdb_utils._duckdb_sqlite_connection"
    ).return_value.__enter__.return_value = mock_conn
    mock_file = mocker.MagicMock()
    mock_file.magic_text = "SQLite database"

    mock_conn.execute.side_effect = Exception("DB Error")

    with pytest.raises(RuntimeError, match="DB Error"):
        run_query(mock_file, "SELECT * FROM foo")


def test_generate_sql_query_success(mocker):
    """Test generate_sql_query success path."""
    mock_llm_manager = mocker.patch("lib.duckdb_utils.manager.LLMManager")
    mock_run_query = mocker.patch("lib.duckdb_utils.run_query")

    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    mock_llm = mocker.MagicMock()
    mock_provider.return_value = mock_llm

    mock_llm.generate.return_value = "SELECT * FROM table;"

    mock_file = mocker.MagicMock()

    result = generate_sql_query(
        llm_provider="google",
        llm_model="gemini-pro",
        tables_schemas="schema",
        user_request="request",
        file=mock_file,
    )

    assert result == "SELECT * FROM table;"
    mock_run_query.assert_called_once_with(mock_file, "SELECT * FROM table;")


def test_generate_sql_query_retry(mocker):
    """Test generate_sql_query retry logic."""
    mock_llm_manager = mocker.patch("lib.duckdb_utils.manager.LLMManager")
    mock_run_query = mocker.patch("lib.duckdb_utils.run_query")

    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    mock_llm = mocker.MagicMock()
    mock_provider.return_value = mock_llm

    mock_llm.generate.side_effect = ["INVALID QUERY", "VALID QUERY"]

    mock_file = mocker.MagicMock()

    # First call to run_query fails, second succeeds
    mock_run_query.side_effect = [RuntimeError("error"), None]

    result = generate_sql_query(
        llm_provider="google",
        llm_model="gemini-pro",
        tables_schemas="schema",
        user_request="request",
        file=mock_file,
    )

    assert result == "VALID QUERY"
    assert mock_llm.generate.call_count == 2
    assert mock_run_query.call_count == 2


def test_generate_sql_query_fail_after_retries(mocker):
    """Test generate_sql_query fails after max retries."""
    mock_llm_manager = mocker.patch("lib.duckdb_utils.manager.LLMManager")
    mock_run_query = mocker.patch("lib.duckdb_utils.run_query")

    mock_manager_instance = mock_llm_manager.return_value
    mock_provider = mocker.MagicMock()
    mock_manager_instance.get_provider.return_value = mock_provider
    mock_llm = mocker.MagicMock()
    mock_provider.return_value = mock_llm

    mock_llm.generate.return_value = "INVALID QUERY"

    mock_file = mocker.MagicMock()
    mock_run_query.side_effect = RuntimeError("error")

    with pytest.raises(RuntimeError, match="Query generation failed after 3 attempts"):
        generate_sql_query(
            llm_provider="google",
            llm_model="gemini-pro",
            tables_schemas="schema",
            user_request="request",
            file=mock_file,
            max_retries=3,
        )
