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

import duckdb
from openrelik_ai_common.providers import manager


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
        dict: A dictionary where keys are table names and values are dictionaries of column names and their
    """
    if not is_sql_file(file.magic_text):
        return {}

    # Set read_only to True to prevent any modifications to the database.
    db_conn = duckdb.connect(file.path, read_only=True)

    # Disable external access to prevent that the query accesses files outside the database.
    db_conn.execute("SET enable_external_access = false;")

    # Query to get all tables and their schemas using DuckDB's information schema.
    tables_schemas_query = """
        SELECT t.table_name, c.column_name, c.data_type
        FROM information_schema.tables t
        JOIN information_schema.columns c
            ON t.table_schema = c.table_schema
            AND t.table_name = c.table_name
        WHERE t.table_type = 'BASE TABLE'
        ORDER BY t.table_schema, t.table_name, c.ordinal_position;
    """

    try:
        # Use .fetchall() to get all rows as a list of tuples
        results = db_conn.execute(tables_schemas_query).fetchall()
        tables_schemas = {}
        for table_name, column_name, data_type in results:
            if table_name not in tables_schemas:
                tables_schemas[table_name] = {}
            tables_schemas[table_name][column_name] = data_type
    except Exception as e:
        raise RuntimeError(e)
    finally:
        db_conn.close()

    return tables_schemas


def run_query(file: object, sql_query: str) -> list[dict]:
    """Run a SQL query on a DuckDB database file and return a list of dictionaries.

    Args:
        file: A SQL database file.
        sql_query: The SQL query to execute.

    Returns:
        list[dict]: The result of the query as a list of dictionaries.
    """
    if not is_sql_file(file.magic_text):
        raise RuntimeError("File is not a supported SQL format.")

    # Set read_only to True to prevent any modifications to the database.
    db_conn = duckdb.connect(file.path, read_only=True)

    # Disable external access to prevent that the query accesses files outside the database.
    db_conn.execute("SET enable_external_access = false;")

    try:
        # Execute the query and get both the data and column names
        cursor = db_conn.execute(sql_query)
        columns = [desc[0] for desc in cursor.description]
        results = cursor.fetchall()

        # Manually create a list of dictionaries
        list_of_dicts = [dict(zip(columns, row)) for row in results]

    except Exception as e:
        raise RuntimeError(e)
    finally:
        db_conn.close()

    return list_of_dicts


def generate_sql_query(
    llm_provider: str, llm_model: str, tables_schemas: str, user_request: str
) -> str:
    """Generate a SQL query based on the database schema and user request.

    Args:
        llm_provider (str): The name of the LLM provider to use.
        llm_model (str): The name of the LLM model to use.
        tables_schemas (str): The database schema information.
        user_request (str): The user's request or question.

    Returns:
        str: The generated SQL query.
    """

    SYSTEM_INSTRUCTION = """
    Given an input question, create a syntactically correct DuckDB SQL query to
    run to help find the answer. Unless the user specifies in his question a
    specific number of examples they wish to obtain, always limit your query to
    at most 10 results. You can order the results by a relevant column to
    return the most interesting examples in the database.

    Never query for all the columns from a specific table, only ask for a the
    few relevant columns given the question.

    Pay attention to use only the column names that you can see in the schema
    description. Be careful to not query for columns that do not exist. Also,
    pay attention to which column is in which table.

    Output format:
    * **ALWAYS** use the LIMIT clause to limit the number of results to at most 10.
    * Return the query in a single line as a string, without any additional text or formatting.
    * Do not include any comments or explanations in the output.
    * Do not use any aliases in the query.
    * Do not return markdown or any other formatting.
    """

    PROMPT = """
    ### Tables and Schemas:
    {tables_schemas}

    ### User Input:
    {user_request}
    """

    provider = manager.LLMManager().get_provider(llm_provider)
    llm = provider(model_name=llm_model, system_instructions=SYSTEM_INSTRUCTION)
    query = llm.generate(
        prompt=PROMPT.format(tables_schemas=tables_schemas, user_request=user_request)
    )

    return query
