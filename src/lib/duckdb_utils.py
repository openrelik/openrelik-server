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
"""Utility functions for working with DuckDB databases."""

import os
from contextlib import contextmanager

import duckdb
from openrelik_ai_common.providers import manager


@contextmanager
def _duckdb_sqlite_connection(file_path: str):
    """Context manager that yields a DuckDB connection with a SQLite file attached.

    Args:
        file_path: Path to the SQLite database file.

    Yields:
        duckdb.DuckDBPyConnection: A configured DuckDB connection with the SQLite file attached.
    """
    SQLITE_EXTENSION_PATH = "/app/openrelik/sqlite_scanner.duckdb_extension"
    db_conn = duckdb.connect()
    try:
        if os.path.exists(SQLITE_EXTENSION_PATH):
            db_conn.execute(f"INSTALL '{SQLITE_EXTENSION_PATH}'; LOAD '{SQLITE_EXTENSION_PATH}';")
        else:
            db_conn.execute("INSTALL sqlite; LOAD sqlite;")

        db_conn.execute("SET enable_external_access = false;")
        db_conn.execute(f"ATTACH '{file_path}' AS sqlite_db (TYPE SQLITE, READ_ONLY TRUE);")
        db_conn.execute("USE sqlite_db;")

        yield db_conn
    finally:
        db_conn.close()


def is_sql_file(magic_text: str) -> bool:
    """Check if file is a valid SQL database file based on magic text.

    Args:
        magic_text: The magic text of the file.

    Returns:
        bool: True if file is a valid SQL database file.
    """
    if not magic_text:
        return False

    magic_text_lower = magic_text.lower()

    # Define supported SQL database types to check against the mime magic text
    sql_database_types = ["sqlite", "duckdb"]

    # Check if the magic text contains "database" and any of the supported SQL database types
    contains_database = "database" in magic_text_lower
    contains_supported_type = any(db_type in magic_text_lower for db_type in sql_database_types)

    return contains_database and contains_supported_type


def get_tables_schemas(file: object) -> dict:
    """Get all tables and their schemas from the DuckDB database.

    Args:
        file: A SQL database file.

    Returns:
        dict: A dictionary where keys are table names and values are dictionaries of column names and their types.
    """
    if not is_sql_file(file.magic_text):
        return {}
    try:
        with _duckdb_sqlite_connection(file.path) as db_conn:
            tables = db_conn.execute(
                "SELECT name FROM main.sqlite_master WHERE type = 'table' ORDER BY name;"
            ).fetchall()
            return {
                table_name: {
                    col[1]: col[2]
                    for col in db_conn.execute(f"PRAGMA table_info('{table_name}');").fetchall()
                }
                for (table_name,) in tables
            }
    except Exception as e:
        raise RuntimeError(e)


def run_query(file: object, sql_query: str) -> list[dict]:
    """Run a SQL query on a SQLite database file and return a list of dictionaries.

    Args:
        file: A SQL database file.
        sql_query: The SQL query to execute.

    Returns:
        list[dict]: The result of the query as a list of dictionaries.
    """
    if not is_sql_file(file.magic_text):
        raise RuntimeError("File is not a supported SQL format.")
    try:
        with _duckdb_sqlite_connection(file.path) as db_conn:
            cursor = db_conn.execute(sql_query)
            columns = [desc[0] for desc in cursor.description]
            results = [
                tuple(str(item) if isinstance(item, bytes) else item for item in row)
                for row in cursor.fetchall()
            ]
            return [dict(zip(columns, row)) for row in results]
    except Exception as e:
        raise RuntimeError(e)


def generate_sql_query(
    llm_provider: str,
    llm_model: str,
    tables_schemas: str,
    user_request: str,
    file: object,
    max_retries: int = 3,
) -> str:
    """Generate a valid SQL query from a natural language request, retrying on failure.

    It uses the LLM to generate a query and then validates it by running it against the database.
    If the query fails, it uses the error message to generate a new query, letting the LLM correct
    its mistakes.

    Args:
        llm_provider (str): The name of the LLM provider to use.
        llm_model (str): The name of the LLM model to use.
        tables_schemas (str): The database schema information.
        user_request (str): The natural language request or question.
        file (object): The SQL database file used to validate the query.
        max_retries (int): Maximum number of generation attempts. Defaults to 3.

    Returns:
        str: A validated SQL query that executed without errors.

    Raises:
        RuntimeError: If a valid query cannot be generated after max_retries attempts.
    """

    SYSTEM_INSTRUCTION = """
    You are an expert SQL query generator for DuckDB querying attached SQLite databases.
    Your sole job is to output a single, valid DuckDB SQL query — nothing else.

    STRICT OUTPUT RULES:
    - Output ONLY the raw SQL query, on a single line
    - No markdown, no backticks, no code fences, no comments, no explanations
    - **ALWAYS** use the LIMIT clause to limit the number of results to at most 10

    QUERY RULES:
    - Only use table and column names that appear exactly in the schema provided — do not invent or guess names
    - Always qualify ambiguous column names with their table name (e.g. table_name.column_name)
    - Use LIMIT 10 unless the user explicitly requests a different number of results
    - Never use SELECT * — only select columns relevant to the question
    - For text matching, use LOWER() on both sides and LIKE for case-insensitive search (e.g. LOWER(col) LIKE LOWER('%value%'))
    - When joining tables, identify the foreign key relationships from the schema before writing the JOIN
    - Always format timestamp outputs as ISO 8601 strings with UTC timezone using strftime. When converting integer timestamps, wrap the conversion in AT TIME ZONE 'UTC':
        strftime(
        CASE
            WHEN column > 1000000000000000 THEN to_timestamp(column / 1000000.0) AT TIME ZONE 'UTC'
            WHEN column > 1000000000000 THEN to_timestamp(column / 1000.0) AT TIME ZONE 'UTC'
            ELSE to_timestamp(column) AT TIME ZONE 'UTC'
        END,
        '%Y-%m-%dT%H:%M:%SZ'
        )
    - If a column stores dates as text, cast with CAST(column AS DATE)
    - If the question cannot be answered from the schema, output exactly: SELECT 'insufficient schema' AS error
    """

    PROMPT = """
    ### Database Schema
    The following tables and columns are available. Use ONLY these — do not reference any others.

    {tables_schemas}

    ### Task
    Write a DuckDB SQL query that answers the following:
    {user_request}

    Remember: output only the raw SQL query, nothing else.
    """

    RETRY_PROMPT = """
    ### Database Schema
    {tables_schemas}

    ### User Input
    {user_request}

    ### Previous Attempt
    Query: {previous_query}
    Error: {error}

    The query above failed with the error shown. Fix the query to resolve this error.
    Remember: output only the raw SQL query, nothing else.
    """

    provider = manager.LLMManager().get_provider(llm_provider)
    llm = provider(model_name=llm_model, system_instructions=SYSTEM_INSTRUCTION)

    query = None
    last_error = None

    for attempt in range(1, max_retries + 1):
        if attempt == 1:
            query = llm.generate(
                prompt=PROMPT.format(
                    tables_schemas=tables_schemas,
                    user_request=user_request,
                )
            ).strip()
        else:
            query = llm.generate(
                prompt=RETRY_PROMPT.format(
                    tables_schemas=tables_schemas,
                    user_request=user_request,
                    previous_query=query,
                    error=last_error,
                )
            ).strip()

        try:
            run_query(file, query)
            return query
        except RuntimeError as e:
            last_error = str(e)
            if attempt == max_retries:
                raise RuntimeError(
                    f"Query generation failed after {max_retries} attempts. "
                    f"Last error: {last_error}"
                )
