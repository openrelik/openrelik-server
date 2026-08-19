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

import os
from contextlib import asynccontextmanager

from celery.app import Celery
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openrelik_common import telemetry
from sqlalchemy import not_, or_, text
from sqlalchemy.exc import ProgrammingError
from starlette.middleware.sessions import SessionMiddleware

from api.v1 import configs as configs_v1
from api.v1 import files as files_v1
from api.v1 import folders as folders_v1
from api.v1 import groups as groups_v1
from api.v1 import metrics as metrics_v1
from api.v1 import schemas
from api.v1 import taskqueue as taskqueue_v1
from api.v1 import users as users_v1
from api.v1 import workflows as workflows_v1
from auth import common as common_auth
from auth import google as google_auth
from auth import local as local_auth
from config import config

if config.get("auth", {}).get("oidc"):
    from auth import oidc as oidc_auth

if config.get("auth", {}).get("iap"):
    from auth import iap as iap_auth

from datastores.sql.crud.group import (
    add_user_to_group,
    create_group_in_db,
    get_group_by_name_from_db,
)
from datastores.sql.database import SessionLocal
from datastores.sql.models.group import Group
from datastores.sql.models.user import User
from healthz import router as healthz_router
from lib import celery_utils

# Allow Frontend origin to make API calls.
origins = config["server"]["allowed_origins"]


async def populate_everyone_group(db):
    everyone_group = get_group_by_name_from_db(db, "Everyone")
    if not everyone_group:
        everyone_group = create_group_in_db(db, schemas.GroupCreate(name="Everyone"))

    # Add users that are not in the "Everyone" group.
    users_to_add = (
        db.query(User)
        .filter(
            or_(
                not_(User.groups.any()),  # Users with no groups
                not_(User.groups.any(Group.id == everyone_group.id)),  # Users not in everyone_group
            )
        )
        .all()
    )
    for user in users_to_add:
        add_user_to_group(db, everyone_group, user)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # This is run before the application accepts requests (before start)
    try:
        db = SessionLocal()
        # Try a simple query that requires the table to exist
        db.execute(text("SELECT 1 FROM user LIMIT 1")).all()
        await populate_everyone_group(db)
    except ProgrammingError:  # Catch table-not-found errors
        pass
    finally:
        db.close()
    yield
    # Anything after the yield is run when the server is shutting down.
    pass


# Create the main app

secret_key = config["auth"].get("secret_session_key")
secret_key_file = config["auth"].get("secret_session_key_file")
if secret_key_file:
    if not os.path.exists(secret_key_file):
        raise FileNotFoundError(f"secret_session_key file not found: {secret_key_file}")
    try:
        with open(secret_key_file, 'r') as f:
            secret_key = f.read().strip()
    except PermissionError:
        raise PermissionError(f"Cannot read secret_session_key file: {secret_key_file}")
    except Exception as e:
        raise RuntimeError(f"Error reading secret_session_key file {secret_key_file}: {e}")

if secret_key is None:
    raise RuntimeError("No secret_session_key provided (c.f. setting auth.secret_session_key)")

app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=secret_key)

# avoid further usage (of course the secret is still stored in the middleware component)
del secret_key

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
if config.get("auth", {}).get("oidc"):
    app.include_router(oidc_auth.router)
if config.get("auth", {}).get("iap"):
    app.include_router(iap_auth.router)
app.include_router(healthz_router)

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
    groups_v1.router,
    prefix="/groups",
    tags=["groups"],
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
    prefix="/folders/{folder_id}/workflows",
    tags=["workflows"],
    dependencies=[
        Depends(common_auth.get_current_active_user),
        Depends(common_auth.verify_csrf),
    ],
)
api_v1.include_router(
    workflows_v1.router_root,
    prefix="/workflows",
    tags=["workflows"],
    dependencies=[
        Depends(common_auth.get_current_active_user),
        Depends(common_auth.verify_csrf),
    ],
)
api_v1.include_router(
    taskqueue_v1.router,
    prefix="/taskqueue",
    tags=["taskqueue"],
    dependencies=[
        Depends(common_auth.get_current_active_user),
        Depends(common_auth.verify_csrf),
    ],
)
api_v1.include_router(
    metrics_v1.router,
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[
        Depends(common_auth.get_current_active_user),
        Depends(common_auth.verify_csrf),
    ],
)

# Setup the queues. This function take all registered tasks on the celery task queue
# and generate the task queue config automatically.
redis_url = os.getenv("REDIS_URL")
celery = Celery(broker=redis_url, backend=redis_url)
telemetry.instrument_fast_api(api_v1, excluded_urls='/files/*/download_stream,/files/*/download,/files/upload')
celery_utils.update_task_queues(celery)
