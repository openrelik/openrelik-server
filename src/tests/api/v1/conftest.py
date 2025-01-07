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

"""Contains pytest fixtures used in multiple unit tests."""

import pytest
import uuid

from typing import Sequence

from datastores.sql.models.group import Group
from datastores.sql.models.user import User as UserModel
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from auth.common import get_current_active_user
from api.v1.configs import router as configs_router
from api.v1.files import router as files_router
from api.v1.folders import router as folders_router
from api.v1.groups import router as groups_router
from api.v1.metrics import router as metrics_router
from api.v1.taskqueue import router as taskqueue_router
from api.v1.users import router as users_router
from api.v1.workflows import router as workflows_router
from api.v1.schemas import (
    User as UserSchema,
    UserCreate as UserCreateSchema,
    UserResponse as UserResponseSchema,
    UserSearchResponse as UserSearchResponseSchema,
    UserApiKeyResponse as UserApiKeyResponseSchema,
)

@pytest.fixture
def db(mocker):
    """Mock database session."""
    mock_db = mocker.MagicMock(spec=Session)
    return mock_db


@pytest.fixture
def example_groups() -> Sequence[Group]:
    groups_data = [
        {"name": "Group 1", "description": "Description 1", "id": 1},  # Add IDs
        {"name": "Group 2", "description": "Description 2", "id": 2},
    ]
    groups = [Group(**data) for data in groups_data]
    return groups


@pytest.fixture
def test_user_db_model() -> UserModel:
    """Database User model for testing."""
    mock_user = UserModel(
        display_name="test_user",
        username="test_user",
        email="test_user@gmail.com",
        profile_picture_url=" http://localhost/profile/pic",
        preferences = "",
        uuid= uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        id = 1,
        created_at = "2025-01-07T18:29:07.772000Z",
        updated_at = "2025-01-07T18:29:07.772000Z",
        deleted_at = None,
        is_admin=False,
        is_robot=False,
        is_active=True,
        auth_method="google",
        password_hash="hashed_password",
        password_hash_algorithm="sha256",
        folders = [],
        files = [],
        workflows = [],
        workflow_templates = [],
        tasks = [],
        api_keys = [],
        user_roles = [],
        groups = []
    )
    return mock_user


@pytest.fixture
def regular_user() -> UserSchema:
    """Regular user fixture."""
    mock_user = UserSchema(
        display_name="test_user",
        username="test_user",
        email="test_user@gmail.com",
        profile_picture_url=" http://localhost/profile/pic",
        uuid= uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        is_active=True,
        id = 100,
        created_at = "2025-01-07T18:29:07.772000Z",
        updated_at = "2025-01-07T18:29:07.772000Z",
        deleted_at = None,
        is_deleted =  False,
        auth_method = "google"
    )
    return mock_user


@pytest.fixture
def user_response() -> UserResponseSchema:
    """User response fixture."""
    mock_user = UserResponseSchema(
        display_name="test_user",
        username="test_user",
        auth_method= "google",
        email="test_user@gmail.com",
        profile_picture_url=" http://localhost/profile/pic",
        uuid= uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        created_at = "2025-01-07T18:29:07.772000Z",
        updated_at = "2025-01-07T18:29:07.772000Z",
        deleted_at = None,
        id = 100,
        is_deleted = False
    )
    return mock_user


@pytest.fixture
def admin_user() -> UserSchema:
    """Admin user fixture."""
    mock_user = UserSchema(
        display_name="admin_user",
        username="admin_user",
        email="admin_user@gmail.com",
        profile_picture_url=" http://localhost/profile/pic",
        uuid= uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        is_active=True,
        id = 1,
        created_at = "2025-01-07T18:29:07.772000Z",
        updated_at = "2025-01-07T18:29:07.772000Z",
        deleted_at = None,
        is_deleted =  False
    )
    return mock_user


@pytest.fixture
def robot_user() -> UserSchema:
    """Robot user fixture."""
    mock_user = UserSchema(
        display_name="robot_user",
        username="robot_user",
        email="robot_user@gmail.com",
        profile_picture_url=" http://localhost/profile/pic",
        uuid= uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        is_active=True,
        id = 1,
        created_at = "2025-01-07T18:29:07.772000Z",
        updated_at = "2025-01-07T18:29:07.772000Z",
        deleted_at = None,
        is_deleted =  False
    )
    return mock_user


@pytest.fixture
def inactive_user() -> UserSchema:
    """Inactive user fixture."""
    mock_user = UserSchema(
        display_name="inactive_user",
        username="inactive_user",
        email="inactive_user@gmail.com",
        profile_picture_url=" http://localhost/profile/pic",
        uuid= uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        is_active=True,
        id = 1,
        created_at = "2025-01-07T18:29:07.772000Z",
        updated_at = "2025-01-07T18:29:07.772000Z",
        deleted_at = None,
        is_deleted =  False
    )
    return mock_user


@pytest.fixture
def user_create_schema() -> UserCreateSchema:
    """User create schema fixture."""
    mock_user = UserCreateSchema(
        display_name="inactive_user",
        username="inactive_user",
        password_hash="hashed_password",
        password_hash_algorithm="sha256",
        auth_method="google",
        email="inactive_user@gmail.com",
        profile_picture_url=" http://localhost/profile/pic",
        uuid= uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        id = 1,
        is_active=True,
        is_admin=False,
        is_robot=False,
        created_at = "2025-01-07T18:29:07.772000Z",
        updated_at = "2025-01-07T18:29:07.772000Z",
        deleted_at = None,
        is_deleted = False
    )
    return mock_user


@pytest.fixture
def user_search_response() -> UserSearchResponseSchema:
    """User search response fixture."""
    mock_search_response = UserSearchResponseSchema(
        display_name="Test User",
        username="test_user",
        profile_picture_url="http://localhost/profile/pic",
        id=1,
        created_at = "2025-01-07T18:29:07.772000Z",
        updated_at = "2025-01-07T18:29:07.772000Z",
        deleted_at = None,
        is_deleted = False
    )
    return mock_search_response


@pytest.fixture
def user_api_key_response() -> Sequence[UserApiKeyResponseSchema]:
    """User API key response fixture."""
    mock_api_key = UserApiKeyResponseSchema(
        display_name="test_key",
        description="test",
        token_exp=1234567890,
        id=1,
        created_at = "2025-01-07T18:29:07.772000Z",
        updated_at = "2025-01-07T18:29:07.772000Z",
        deleted_at = None,
        is_deleted = False
    )
    return [mock_api_key.model_dump(mode="json")]


@pytest.fixture
def fastapi_test_client(user_response) -> TestClient:
    """This fixture sets up a FastAPI test client for the OpenRelik v1 API."""
    app: FastAPI = FastAPI()
    # Set up all the necessary FastAPI routes.
    app.include_router(
        taskqueue_router, prefix="/taskqueue", tags=["taskqueue"], dependencies=[]
    )
    app.include_router(
        configs_router, prefix="/configs", tags=["configs"], dependencies=[]
    )
    app.include_router(files_router, prefix="/files", tags=["files"], dependencies=[])
    app.include_router(
        folders_router, prefix="/folders", tags=["folders"], dependencies=[]
    )
    app.include_router(
        groups_router, prefix="/groups", tags=["groups"], dependencies=[]
    )
    app.include_router(
        metrics_router, prefix="/metrics", tags=["metrics"], dependencies=[]
    )
    app.include_router(users_router, prefix="/users", tags=["users"], dependencies=[])
    app.include_router(
        workflows_router, prefix="/workflows", tags=["workflows"], dependencies=[]
    )
    # Override authentication check dependency injection.
    app.dependency_overrides[
        get_current_active_user
    ] = lambda: user_response
    # We will use a fastapi.TestClient object to test the API endpoints.
    client = TestClient(app)
    return client
