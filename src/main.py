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

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from healthz import router as healthz_router
from config import config
from datastores.sql.crud.group import (
    add_user_to_group,
    create_group_in_db,
    get_group_by_name_from_db,
)
from datastores.sql.database import SessionLocal
from datastores.sql.models.group import Group
from datastores.sql.models.user import User
from lib import celery_utils
import os
from celery.app import Celery

from opentelemetry import trace

from opentelemetry.exporter.otlp.proto.grpc import trace_exporter as grpc_trace_exporter
from opentelemetry.exporter.otlp.proto.http import trace_exporter as http_trace_exporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

import logging

logging.basicConfig(level=logging.DEBUG)

# Allow Frontend origin to make API calls.
origins = config["server"]["allowed_origins"]


async def populate_everyone_group(db):
    everyone_group = get_group_by_name_from_db(db, "Everyone")
    if not everyone_group:
        everyone_group = create_group_in_db(
            db, schemas.GroupCreate(name="Everyone"))

    # Add users that are not in the "Everyone" group.
    users_to_add = (
        db.query(User)
        .filter(
            or_(
                not_(User.groups.any()),  # Users with no groups
                not_(
                    User.groups.any(Group.id == everyone_group.id)
                ),  # Users not in everyone_group
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


def setup_telemetry(service_name: str):

    resource = Resource(attributes={
        "service.name": service_name
    })

    # --- Tracing Setup ---
    trace.set_tracer_provider(TracerProvider(resource=resource))

    otel_mode = os.environ.get("OTEL_MODE", "otlp-grpc")
    otlp_grpc_endpoint = os.environ.get("OTLP_GRPC_ENDPOINT", "jaeger-collector:4317")
    otlp_http_endpoint = os.environ.get("OTLP_HTTP_ENDPOINT", "http://jaeger-collector:4318/v1/traces")

    trace_exporter = None
    if otel_mode == "otlp-grpc":
        trace_exporter = grpc_trace_exporter.OTLPSpanExporter(
                endpoint=otlp_grpc_endpoint, insecure=True)
        logging.info(f"Sending OTLP data via GRPC to {otlp_grpc_endpoint}")
    elif otel_mode == "otlp-http":
        trace_exporter = http_trace_exporter.OTLPSpanExporter(
                endpoint=otlp_http_endpoint)
        logging.info(f"Sending OTLP data via HTTP to {otlp_http_endpoint}")
    else:
        raise Exception("Unsupported OTEL tracing mode %s", otel_mode)

    trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(trace_exporter))



setup_telemetry("openrelik-server")

# Create the main app
app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware,
                   secret_key=config["auth"]["secret_session_key"])


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

FastAPIInstrumentor.instrument_app(api_v1)

# Setup the queues. This function take all registered tasks on the celery task queue
# and generate the task queue config automatically.
redis_url = os.getenv("REDIS_URL")
celery = Celery(broker=redis_url, backend=redis_url)
celery_utils.update_task_queues(celery)
