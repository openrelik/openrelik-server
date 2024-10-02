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

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from api.v1 import configs as configs_v1
from api.v1 import files as files_v1
from api.v1 import folders as folders_v1
from api.v1 import users as users_v1
from api.v1 import workflows as workflows_v1
from auth import common as common_auth
from auth import google as google_auth
from auth import local as local_auth
from config import config
from datastores.sql import database

# Allow Frontend origin to make API calls.
origins = config["server"]["allowed_origins"]

# Initialize database
database.BaseModel.metadata.create_all(bind=database.engine)

# Create the main app
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=config["auth"]["secret_session_key"])

# Create app for API version 1
api_v1 = FastAPI()

# Mount the API app
app.mount("/api/v1", api_v1)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication providers
app.include_router(common_auth.router)
app.include_router(local_auth.router)
app.include_router(google_auth.router)

# Routes
api_v1.include_router(
    users_v1.router,
    prefix="/users",
    tags=["users"],
    dependencies=[
        Depends(common_auth.get_current_active_user),
        Depends(common_auth.verify_csrf),
    ],
)
api_v1.include_router(
    configs_v1.router,
    prefix="/configs",
    tags=["configs"],
    dependencies=[
        Depends(common_auth.get_current_active_user),
        Depends(common_auth.verify_csrf),
    ],
)
api_v1.include_router(
    files_v1.router,
    prefix="/files",
    tags=["files"],
    dependencies=[
        Depends(common_auth.get_current_active_user),
        Depends(common_auth.verify_csrf),
    ],
)
api_v1.include_router(
    folders_v1.router,
    prefix="/folders",
    tags=["folders"],
    dependencies=[
        Depends(common_auth.get_current_active_user),
        Depends(common_auth.verify_csrf),
    ],
)
api_v1.include_router(
    workflows_v1.router,
    prefix="/workflows",
    tags=["workflows"],
    dependencies=[
        Depends(common_auth.get_current_active_user),
        Depends(common_auth.verify_csrf),
    ],
)
