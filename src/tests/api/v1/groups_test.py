# Copyright 2024 Google LLC
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

"""Tests for groups endpoints."""


def test_get_all_groups(
    fastapi_test_client, db, example_groups, mocker
):
    """Test the get_all_groups endpoint."""
    mock_query = mocker.patch("sqlalchemy.orm.Session.query")
    mock_query.return_value = db.query
    mock_query.return_value.all.return_value = example_groups

    response = fastapi_test_client.get("/groups/")

    assert response.status_code == 200
    groups = response.json()
    assert len(groups) == 2
    assert groups[0]["name"] == "Group 1"
    assert groups[0]["description"] == "Description 1"
    assert groups[0]["id"] == 1  # Now you can assert on ID
    assert groups[1]["name"] == "Group 2"
    assert groups[1]["description"] == "Description 2"
    assert groups[1]["id"] == 2
