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

from typing import List

from sqlalchemy.orm import Session
from datastores.sql.models.group import Group
import pytest


@pytest.fixture
def db(mocker):
    """Mock database session."""
    mock_db = mocker.MagicMock(spec=Session)
    return mock_db


@pytest.fixture
def example_groups(db: Session) -> List[Group]:
    groups_data = [
        {"name": "Group 1", "description": "Description 1", "id": 1},  # Add IDs
        {"name": "Group 2", "description": "Description 2", "id": 2},
    ]
    groups = [Group(**data) for data in groups_data]
    db.query.all.return_value = groups
    return groups


def test_get_all_groups(
    fastapi_test_client, db: Session, example_groups: List[Group], mocker
):
    # Patch the query dependency to return the mock db
    with mocker.patch("sqlalchemy.orm.Session.query", return_value=db.query):
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
