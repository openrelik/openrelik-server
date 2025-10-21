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


from lib import duckdb_utils


def test_is_sql_file():
    assert duckdb_utils.is_sql_file("SQLite 3.x database") is True
    assert duckdb_utils.is_sql_file("DuckDB database") is True
    assert duckdb_utils.is_sql_file("Some other database") is False
    assert duckdb_utils.is_sql_file("Just some text") is False
    assert duckdb_utils.is_sql_file("") is False
    assert duckdb_utils.is_sql_file(None) is False
