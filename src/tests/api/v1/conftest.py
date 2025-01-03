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

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.v1.configs import router as configs_router
from api.v1.files import router as files_router
from api.v1.folders import router as folders_router
from api.v1.groups import router as groups_router
from api.v1.metrics import router as metrics_router
from api.v1.taskqueue import router as taskqueue_router
from api.v1.users import router as users_router
from api.v1.workflows import router as workflows_router
import pytest


@pytest.fixture
def fastapi_test_client():
    """This fixture sets up a FastAPI test client for the OpenRelik v1 API."""
    app = FastAPI()
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
    client = TestClient(app)
    return client
