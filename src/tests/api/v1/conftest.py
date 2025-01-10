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
import os

from httpx import ASGITransport, AsyncClient
from typing import Sequence

from datastores.sql.database import get_db_connection
from datastores.sql.models.group import Group
from datastores.sql.models.user import User as UserModel
from datastores.sql.models.file import File as FileModel
from datastores.sql.models.folder import Folder as FolderModel
from datastores.sql.models.workflow import Task as TaskModel, Workflow as WorkflowModel
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
    FolderResponse as FolderResponseSchema,
    FolderResponseCompact as FolderResponseCompactSchema,
    FileResponseCompactList as FileResponseCompactListSchema,
    FileResponse as FileResponseSchema,
    User as UserSchema,
    UserResponse as UserResponseSchema,
    UserResponseCompact as UserResponseCompactSchema,
    UserSearchResponse as UserSearchResponseSchema,
    UserApiKeyResponse as UserApiKeyResponseSchema,
    Task as TaskSchema,
    Workflow as WorkflowSchema,
)


@pytest.fixture(autouse=True)
def authz(mocker):
    mock_authz = mocker.patch("datastores.sql.crud.authz.check_user_access")
    mock_authz.return_value = True
    return mock_authz


@pytest.fixture
def db(mocker):
    """Mock database session fixture.  Autouse makes it apply to all tests."""
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
def task_schema_mock(user_db_model, workflow_schema_mock) -> TaskSchema:
    """Fixture for a mock TaskResponse object."""
    user_mock = UserSchema.model_validate(user_db_model, from_attributes=True)

    task_data = {
        "id": 1,
        "description": "test task description",
        "display_name": "test task",
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "is_deleted": False,
        "status_short": "pending",
        "status_detail": "Task is pending",
        "status_progress": "Task is pending",
        "result": "{}",
        "runtime": 1.23,
        "user": user_mock,
        "output_files": [],
        "file_reports": [],
        "error_traceback": None,
        "error_exception": None,
        "config": None,
        "workflow": workflow_schema_mock,
    }
    mock_task_response = TaskSchema(**task_data)
    return mock_task_response


@pytest.fixture
def file_response_cloud_disk_File(
    tmp_path, user_db_model, folder_db_model
) -> FileResponseSchema:
    """Fixture for a mock FileResponse object."""
    file_id = 1
    display_name = "test_disk.json"
    path = os.path.join(tmp_path, display_name)

    with open(path, "w") as f:
        f.write("Dummy file content")

    file_size = os.path.getsize(path)

    user_response_compact = UserResponseCompactSchema.model_validate(
        user_db_model, from_attributes=True
    )
    file_data = {
        "id": file_id,
        "display_name": display_name,
        "description": "Test file description",
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        "filename": "test_disk",
        "filesize": file_size,
        "extension": "json",
        "original_path": path,
        "magic_text": "openrelik:test_cloud_provider:disk",
        "magic_mime": "openrelik:test_cloud_provider:disk",
        "data_type": "openrelik:test_cloud_provider:disk",
        "hash_md5": "test_md5",
        "hash_sha1": "test_sha1",
        "hash_sha256": "test_sha256",
        "hash_ssdeep": "test_ssdeep",
        "user_id": 1,
        "user": user_response_compact,
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "folder": folder_db_model,
        "source_file": None,
        "workflows": [],
        "summaries": [],
        "reports": [],
        "is_deleted": False,
    }
    mock_file_response = FileResponseSchema(**file_data)
    return mock_file_response


@pytest.fixture
def file_response(tmp_path, user_db_model, folder_db_model) -> FileResponseSchema:
    """Fixture for a mock FileResponse object."""
    file_id = 1
    display_name = "test_file.txt"
    path = os.path.join(tmp_path, display_name)

    # Create a dummy file for content tests (avoiding FileNotFoundError)
    with open(path, "w") as f:
        f.write("Dummy file content")

    file_size = os.path.getsize(path)

    user_response_compact = UserResponseCompactSchema.model_validate(
        user_db_model, from_attributes=True
    )
    file_data = {
        "id": file_id,
        "display_name": display_name,
        "description": "Test file description",
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        "filename": "test_file",
        "filesize": file_size,
        "extension": "txt",
        "original_path": path,
        "magic_text": "plain text",
        "magic_mime": "text/plain",
        "data_type": "text/plain",
        "hash_md5": "test_md5",
        "hash_sha1": "test_sha1",
        "hash_sha256": "test_sha256",
        "hash_ssdeep": "test_ssdeep",
        "user_id": 1,
        "user": user_response_compact,
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "folder": folder_db_model,
        "source_file": None,
        "workflows": [],
        "summaries": [],
        "reports": [],
        "is_deleted": False,
    }
    mock_file_response = FileResponseSchema(**file_data)
    return mock_file_response


@pytest.fixture
def file_response_compact_list(user_db_model) -> FileResponseCompactListSchema:
    """Fixture for a mock FileResponseCompactList object."""
    user_response_compact = UserResponseCompactSchema.model_validate(
        user_db_model, from_attributes=True
    )
    file_data = {
        "id": 1,
        "display_name": "test_file.txt",
        "filesize": 1024,
        "magic_mime": "text/plain",
        "data_type": "text/plain",
        "user": user_response_compact,
        "created_at": None,
        "is_deleted": False,
    }
    mock_file_response = FileResponseCompactListSchema(**file_data)
    return mock_file_response


@pytest.fixture
def folder_response_compact(user_db_model) -> FolderResponseCompactSchema:
    """Fixture for a mock FolderResponseCompactSchema object."""
    user_response_compact = UserResponseCompactSchema.model_validate(
        user_db_model, from_attributes=True
    )
    folder_data = {
        "id": 1,
        "display_name": "test_folder",
        "description": "test_folder",
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        "user": user_response_compact,
        "selectable": False,
        "workflows": [],
        "user_roles": [],
        "group_roles": [],
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "is_deleted": False,
    }
    mock_folder_response = FolderResponseCompactSchema(**folder_data)
    return mock_folder_response


@pytest.fixture
def folder_response(user_db_model) -> FolderResponseSchema:
    """Fixture for a mock FolderResponseSchema object."""
    user_response_compact = UserResponseCompactSchema.model_validate(
        user_db_model, from_attributes=True
    )
    folder_data = {
        "id": 1,
        "display_name": "test_folder",
        "description": "test_folder",
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        "user": user_response_compact,
        "selectable": False,
        "workflows": [],
        "user_roles": [],
        "group_roles": [],
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "is_deleted": False,
    }
    mock_folder_response = FolderResponseSchema(**folder_data)
    return mock_folder_response


@pytest.fixture
def task_db_model(workflow_db_model, user_db_model) -> TaskModel:
    """Fixture for a mock Task database model object."""
    task_data = {
        "id": 1,
        "display_name": "test task",
        "description": "test task description",
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        "config": None,
        "created_at": None,  # or use a datetime object
        "updated_at": None,  # or use a datetime object
        "deleted_at": None,  # or use a datetime object
        "is_deleted": False,
        "workflow_id": workflow_db_model.id,
        "workflow": workflow_db_model,
        "user_id": user_db_model.id,
        "user": user_db_model,
        "status_short": "pending",
        "status_detail": "Task is pending",
        "status_progress": "Task is pending",
        "result": "{}",  # or use a dict
        "runtime": 1.23,  # or use a float
        "error_exception": None,
        "error_traceback": None,
        "input_files": [],
        "output_files": [],
        "file_reports": [],
    }
    mock_task = TaskModel(**task_data)
    return mock_task


@pytest.fixture
def workflow_schema_mock(folder_db_model, user_db_model) -> WorkflowSchema:
    """Fixture for a mock WorkflowResponse object."""
    workflow_data = {
        "id": 1,
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa7"),
        "display_name": "test workflow",
        "description": "test workflow description",
        "spec_json": None,
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "is_deleted": False,
        "user_id": user_db_model.id,
        "folder_id": folder_db_model.id,
        "file_ids": [],
    }

    mock_workflow_response = WorkflowSchema(**workflow_data)
    return mock_workflow_response


@pytest.fixture
def workflow_db_model(folder_db_model, user_db_model):
    """Fixture for a mock WorkflowResponse object."""
    workflow_data = {
        "id": 1,
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa7"),
        "display_name": "test workflow",
        "description": "test workflow description",
        "spec_json": None,
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "is_deleted": False,
        "user": user_db_model,
        "user_id": user_db_model.id,
        "folder": folder_db_model,
        "folder_id": folder_db_model.id,
        "files": [],
        "tasks": [],
    }

    mock_workflow_response = WorkflowModel(**workflow_data)
    return mock_workflow_response


@pytest.fixture
def file_db_model(tmp_path, user_db_model, folder_db_model) -> FileModel:
    """Fixture for a mock FileResponse object."""
    file_id = 1
    display_name = "test_file.txt"
    folder_path = os.path.join(tmp_path, folder_db_model.uuid.hex)
    os.makedirs(folder_path, exist_ok=True)
    path = os.path.join(folder_path, display_name)  # Use tmp_path for a temporary file

    # Create a dummy file for content tests (avoiding FileNotFoundError)
    with open(path, "w") as f:
        f.write("Dummy file content")

    file_size = os.path.getsize(path)

    # Using a dictionaries to easily initialize the mock
    file_data = {
        "id": file_id,
        "display_name": display_name,
        "description": "Test file description",
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        "filename": "test_file",
        "filesize": file_size,
        "extension": "txt",
        "original_path": path,
        "magic_text": "plain text",
        "magic_mime": "text/plain",
        "data_type": "text/plain",
        "hash_md5": "test_md5",
        "hash_sha1": "test_sha1",
        "hash_sha256": "test_sha256",
        "hash_ssdeep": "test_ssdeep",
        "user_id": 1,
        "user": user_db_model,
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "folder": folder_db_model,
        "folder_id": folder_db_model.id,
        "source_file": None,
        "workflows": [],
        "summaries": [],
        "reports": [],
        "is_deleted": False,
    }
    mock_file_response = FileModel(**file_data)
    return mock_file_response


@pytest.fixture
def file_db_model(tmp_path, user_db_model, folder_db_model) -> FileModel:
    """Fixture for a mock FileModel object."""
    file_id = 1
    display_name = "test_file.txt"
    folder_path = os.path.join(tmp_path, folder_db_model.uuid.hex)
    os.makedirs(folder_path, exist_ok=True)
    path = os.path.join(folder_path, display_name)  # Use tmp_path for a temporary file

    # Create a dummy file for content tests (avoiding FileNotFoundError)
    with open(path, "w") as f:
        f.write("Dummy file content")

    file_size = os.path.getsize(path)

    # Using a dictionaries to easily initialize the mock
    file_data = {
        "id": file_id,
        "display_name": display_name,
        "description": "Test file description",
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        "filename": "test_file",
        "filesize": file_size,
        "extension": "txt",
        "original_path": path,
        "magic_text": "plain text",
        "magic_mime": "text/plain",
        "data_type": "text/plain",
        "hash_md5": "test_md5",
        "hash_sha1": "test_sha1",
        "hash_sha256": "test_sha256",
        "hash_ssdeep": "test_ssdeep",
        "user_id": 1,
        "user": user_db_model,
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "folder": folder_db_model,
        "folder_id": folder_db_model.id,
        "source_file": None,
        "workflows": [],
        "summaries": [],
        "reports": [],
        "is_deleted": False,
    }
    mock_file_response = FileModel(**file_data)
    return mock_file_response


@pytest.fixture
def folder_db_model(user_db_model) -> FolderModel:
    """Fixture for a mock FolderModel object."""

    folder_data = {
        "display_name": "test_folder",
        "description": "test_folder",
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        "user_id": 1,
        "attributes": [],
        "user": user_db_model,
        "files": [],
        "workflows": [],
        "parent_id": 1,
        "parent": None,
        "children": [],
        "user_roles": [],
        "group_roles": [],
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "id": 1,
        "is_deleted": False,
    }

    mock_folder_response = FolderModel(**folder_data)
    return mock_folder_response


@pytest.fixture
def user_db_model() -> UserModel:
    """Database User model for testing."""
    mock_user = UserModel(
        display_name="test_user",
        username="test_user",
        email="test_user@gmail.com",
        profile_picture_url=" http://localhost/profile/pic",
        preferences="",
        uuid=uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        id=1,
        created_at="2025-01-07T18:29:07.772000Z",
        updated_at="2025-01-07T18:29:07.772000Z",
        deleted_at=None,
        is_admin=False,
        is_robot=False,
        is_active=True,
        auth_method="google",
        password_hash="hashed_password",
        password_hash_algorithm="sha256",
        folders=[],
        files=[],
        workflows=[],
        workflow_templates=[],
        tasks=[],
        api_keys=[],
        user_roles=[],
        groups=[],
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
        uuid=uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        is_active=True,
        id=100,
        created_at="2025-01-07T18:29:07.772000Z",
        updated_at="2025-01-07T18:29:07.772000Z",
        deleted_at=None,
        is_deleted=False,
        auth_method="google",
    )
    return mock_user


@pytest.fixture
def user_response() -> UserResponseSchema:
    """User response fixture."""
    mock_user = UserResponseSchema(
        display_name="test_user",
        username="test_user",
        auth_method="google",
        email="test_user@gmail.com",
        profile_picture_url=" http://localhost/profile/pic",
        uuid=uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        created_at="2025-01-07T18:29:07.772000Z",
        updated_at="2025-01-07T18:29:07.772000Z",
        deleted_at=None,
        id=100,
        is_deleted=False,
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
        created_at="2025-01-07T18:29:07.772000Z",
        updated_at="2025-01-07T18:29:07.772000Z",
        deleted_at=None,
        is_deleted=False,
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
        created_at="2025-01-07T18:29:07.772000Z",
        updated_at="2025-01-07T18:29:07.772000Z",
        deleted_at=None,
        is_deleted=False,
    )
    return [mock_api_key.model_dump(mode="json")]


@pytest.fixture
def fastapi_async_test_client(setup_test_app) -> AsyncClient:
    """This fixture sets up an AsyncClient for the OpenRelik v1 API."""
    async_client = AsyncClient(
        transport=ASGITransport(setup_test_app), base_url="http://test"
    )
    return async_client


@pytest.fixture
def fastapi_test_client(setup_test_app) -> TestClient:
    """This fixture sets up a FastAPI test client for the OpenRelik v1 API."""
    client = TestClient(setup_test_app)
    return client


@pytest.fixture
def setup_test_app(user_response, db) -> FastAPI:
    """Set up the FastAPI application for testing."""
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
    app.dependency_overrides[get_current_active_user] = lambda: user_response
    app.dependency_overrides[get_db_connection] = lambda: db
    return app
