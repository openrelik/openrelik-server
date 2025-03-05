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
import json
from httpx import ASGITransport, AsyncClient
from typing import Sequence

from datastores.sql.database import get_db_connection
from datastores.sql.models.group import Group
from datastores.sql.models.user import User
from datastores.sql.models.file import File
from datastores.sql.models.folder import Folder
from datastores.sql.models.workflow import Workflow
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from auth.common import get_current_active_user
from api.v1 import schemas
from api.v1.configs import router as configs_router
from api.v1.files import router as files_router
from api.v1.folders import router as folders_router
from api.v1.groups import router as groups_router
from api.v1.metrics import router as metrics_router
from api.v1.taskqueue import router as taskqueue_router
from api.v1.users import router as users_router
from api.v1.workflows import (
    router as workflows_router,
    router_root as workflows_root_router,
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
def task_response(user_db_model, workflow_schema_mock) -> schemas.TaskResponse:
    """Fixture for a mock TaskResponse object."""
    user_mock = schemas.UserResponse.model_validate(user_db_model, from_attributes=True)
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
        "task_report": None,
        "error_traceback": None,
        "error_exception": None,
        "workflow": workflow_schema_mock,
    }
    mock_task_response = schemas.TaskResponse(**task_data)
    return mock_task_response


@pytest.fixture
def file_response(tmp_path, user_db_model, folder_db_model) -> schemas.FileResponse:
    """Fixture for a mock FileResponse object."""
    file_id = 1
    display_name = "test_file.txt"
    path = os.path.join(tmp_path, display_name)

    # Create a dummy file for content tests (avoiding FileNotFoundError)
    with open(path, "w") as f:
        f.write("Dummy file content")

    file_size = os.path.getsize(path)

    user_response_compact = schemas.UserResponseCompact.model_validate(
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
    mock_file_response = schemas.FileResponse(**file_data)
    return mock_file_response


@pytest.fixture
def file_response_compact_list(user_db_model) -> schemas.FileResponseCompactList:
    """Fixture for a mock FileResponseCompactList object."""
    user_response_compact = schemas.UserResponseCompact.model_validate(
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
    mock_file_response = schemas.FileResponseCompactList(**file_data)
    return mock_file_response


@pytest.fixture
def folder_response_compact(user_db_model) -> schemas.FolderResponseCompact:
    """Fixture for a mock schemas.FolderResponseCompact object."""
    user_response_compact = schemas.UserResponseCompact.model_validate(
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
    mock_folder_response = schemas.FolderResponseCompact(**folder_data)
    return mock_folder_response


@pytest.fixture
def folder_response(user_db_model) -> schemas.FolderResponse:
    """Fixture for a mock schemas.FolderResponse object."""
    user_response_compact = schemas.UserResponseCompact.model_validate(
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
    mock_folder_response = schemas.FolderResponse(**folder_data)
    return mock_folder_response


@pytest.fixture
def workflow_schema_mock(folder_db_model, user_db_model) -> schemas.Workflow:
    """Fixture for a mock WorkflowResponse object."""
    workflow_data = {
        "id": 1,
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa7"),
        "display_name": "test workflow",
        "description": "test workflow description",
        "spec_json": json.dumps(
            {
                "workflow": {
                    "type": "chain",
                    "tasks": [
                        {
                            "type": "task",
                            "task_name": "task_1",
                            "queue_name": "default",
                            "task_config": {"arg_1": "value_1", "arg_2": 2},
                            "tasks": [],
                        },
                        {
                            "type": "task",
                            "task_name": "task_2",
                            "queue_name": "default",
                            "task_config": {},
                            "tasks": [],
                        },
                    ],
                }
            }
        ),
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "is_deleted": False,
        "user_id": user_db_model.id,
        "folder_id": folder_db_model.id,
        "file_ids": [],
    }

    mock_workflow_response = schemas.Workflow(**workflow_data)
    return mock_workflow_response


@pytest.fixture
def workflow_response(user_db_model) -> schemas.WorkflowResponse:
    """Fixture for a mock WorkflowResponse object."""
    user_response_compact = schemas.UserResponseCompact.model_validate(
        user_db_model, from_attributes=True
    )
    workflow_data = {
        "id": 1,
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa7"),
        "display_name": "test workflow",
        "description": "test workflow description",
        "spec_json": json.dumps(
            {
                "workflow": {
                    "type": "chain",
                    "tasks": [
                        {
                            "type": "task",
                            "task_name": "task_1",
                            "queue_name": "default",
                            "task_config": {"arg_1": "value_1", "arg_2": 2},
                            "tasks": [],
                        },
                        {
                            "type": "task",
                            "task_name": "task_2",
                            "queue_name": "default",
                            "task_config": {},
                            "tasks": [],
                        },
                    ],
                }
            }
        ),
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "is_deleted": False,
        "files": [],
        "tasks": [],
        "folder": None,
        "user": user_response_compact,
    }

    mock_workflow_response = schemas.WorkflowResponse(**workflow_data)
    return mock_workflow_response


@pytest.fixture
def workflow_db_model(folder_db_model, user_db_model) -> Workflow:
    """Database Workflow model for testing."""
    workflow_data = {
        "id": 1,
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa7"),  # Or any valid UUID
        "display_name": "test workflow",
        "description": "test workflow description",
        "spec_json": json.dumps(
            {
                "workflow": {
                    "type": "chain",
                    "tasks": [
                        {
                            "type": "task",
                            "task_name": "task_1",
                            "queue_name": "default",
                            "task_config": {"arg_1": "value_1", "arg_2": 2},
                            "tasks": [],
                        },
                        {
                            "type": "task",
                            "task_name": "task_2",
                            "queue_name": "default",
                            "task_config": {},
                            "tasks": [],
                        },
                    ],
                }
            }
        ),
        "created_at": None,  # Or a datetime object if needed
        "updated_at": None,  # Or a datetime object if needed
        "deleted_at": None,  # Or a datetime object if needed
        "is_deleted": False,
        "user_id": user_db_model.id,  # Replace with an actual user ID
        "folder_id": folder_db_model.id,  # Replace with an actual folder ID
        "files": [],  # List of File database models, if relationships already exist
        "tasks": [],
        "folder": folder_db_model,
        "user": user_db_model,
    }

    workflow_db_model = Workflow(**workflow_data)
    return workflow_db_model


@pytest.fixture
def workflow_template_response(user_db_model) -> schemas.WorkflowTemplateResponse:
    """Fixture for a mock WorkflowTemplateResponse object."""
    workflow_data = {
        "id": 1,
        "display_name": "test workflow",
        "spec_json": json.dumps(
            {
                "workflow": {
                    "type": "chain",
                    "tasks": [
                        {
                            "type": "task",
                            "task_name": "task_1",
                            "queue_name": "default",
                            "task_config": {"arg_1": "value_1", "arg_2": 2},
                            "tasks": [],
                        },
                        {
                            "type": "task",
                            "task_name": "task_2",
                            "queue_name": "default",
                            "task_config": {},
                            "tasks": [],
                        },
                    ],
                }
            }
        ),
        "created_at": None,  # Or a datetime object if needed
        "updated_at": None,  # Or a datetime object if needed
        "deleted_at": None,  # Or a datetime object if needed
        "is_deleted": False,
        "user_id": user_db_model.id,  # Replace with an actual user ID
    }
    workflow_template_response = schemas.WorkflowTemplateResponse(**workflow_data)
    return workflow_template_response


@pytest.fixture
def file_db_model(tmp_path, user_db_model, folder_db_model) -> File:
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
    mock_file_response = File(**file_data)
    return mock_file_response


@pytest.fixture
def folder_db_model(user_db_model) -> Folder:
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

    mock_folder_response = Folder(**folder_data)
    return mock_folder_response


@pytest.fixture
def user_db_model() -> User:
    """Database User model for testing."""
    user_data = {
        "display_name": "test_user",
        "username": "test_user",
        "email": "test_user@gmail.com",
        "profile_picture_url": "http://localhost/profile/pic",
        "preferences": None,
        "uuid": uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        "id": 1,
        "created_at": "2025-01-07T18:29:07.772000Z",
        "updated_at": "2025-01-07T18:29:07.772000Z",
        "deleted_at": None,
        "is_admin": False,
        "is_robot": False,
        "is_active": True,
        "auth_method": "google",
        "password_hash": "hashed_password",
        "password_hash_algorithm": "sha256",
        "folders": [],
        "files": [],
        "workflows": [],
        "workflow_templates": [],
        "tasks": [],
        "api_keys": [],
        "user_roles": [],
        "groups": [],
    }
    mock_user = User(**user_data)
    return mock_user


@pytest.fixture
def regular_user() -> schemas.User:
    """Regular user fixture."""
    mock_user = schemas.User(
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
def user_response() -> schemas.UserResponse:
    """User response fixture."""
    mock_user = schemas.UserResponse(
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
def user_api_key_response() -> Sequence[schemas.UserApiKeyResponse]:
    """User API key response fixture."""
    mock_api_key = schemas.UserApiKeyResponse(
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
        workflows_root_router, prefix="/workflows", tags=["workflows"], dependencies=[]
    )
    app.include_router(
        workflows_router,
        prefix="/folders/{folder_id}/workflows",
        tags=["workflows"],
    )
    # Override authentication check dependency injection.
    app.dependency_overrides[get_current_active_user] = lambda: user_response
    app.dependency_overrides[get_db_connection] = lambda: db
    return app
