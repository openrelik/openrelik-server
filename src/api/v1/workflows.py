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

import ast
import json
import os
import re
from typing import List
from uuid import uuid4

from celery import chain as celery_chain
from celery import group as celery_group
from celery import signature
from celery.app import Celery
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from auth.google import get_current_active_user
from datastores.sql.crud.folder import create_folder_in_db
from datastores.sql.crud.workflow import (
    get_workflow_from_db,
    create_workflow_in_db,
    delete_workflow_from_db,
    update_workflow_in_db,
    create_task_in_db,
    create_workflow_template_in_db,
    get_workflow_template_from_db,
    get_workflow_templates_from_db,
)
from datastores.sql.models.workflow import Task
from datastores.sql.database import get_db_connection

from . import schemas
from config import config

redis_url = os.getenv("REDIS_URL")
celery = Celery(broker=redis_url, backend=redis_url)

# Setup the queues
# TODO: Generate this from TaskInfo
celery.conf.task_routes = {
    "openrelik_worker_strings.tasks.*": {"queue": "openrelik_worker_strings"},
    "openrelik_worker_plaso.tasks.*": {"queue": "openrelik_worker_plaso"},
    "openrelik_worker_hayabusa.tasks.*": {"queue": "openrelik_worker_hayabusa"},
}

router = APIRouter()


def replace_uuids(data: dict | list, replace_with: str = None) -> dict | list:
    """Replaces UUIDs with placeholder value for the template.

    Args:
        data (dict or list): The data to replace UUIDs in.

    Returns:
        dict or list: The data with UUIDs replaced.
    """

    if isinstance(data, dict):
        for key, value in data.items():
            if key == "uuid":
                if not replace_with:
                    data[key] = uuid4().hex
                else:
                    data[key] = replace_with
            else:
                replace_uuids(value)
    elif isinstance(data, list):
        for item in data:
            replace_uuids(item)


# Get workflow
@router.get("/{workflow_id}", response_model=schemas.WorkflowResponse)
async def get_workflow(workflow_id: int, db: Session = Depends(get_db_connection)):
    return get_workflow_from_db(db, workflow_id)


# Create workflow
@router.post("/", response_model=schemas.WorkflowResponse)
async def create_workflow(
    request_body: schemas.WorkflowCreateRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):

    default_workflow_display_name = "Untitled workflow"
    default_spec_json = None

    if request_body.template_id:
        template = get_workflow_template_from_db(db, request_body.template_id)
        default_workflow_display_name = template.display_name
        spec_json = json.loads(template.spec_json)
        # Replace UUIDs with placeholder value for the template
        replace_uuids(spec_json)
        default_spec_json = json.dumps(spec_json)

    # Create new folder for workflow results
    new_folder = schemas.FolderCreateRequest(
        display_name=default_workflow_display_name, parent_id=request_body.folder_id
    )
    new_workflow_folder = create_folder_in_db(db, new_folder, current_user)

    # Create new workflow
    new_workflow_db = schemas.Workflow(
        display_name=default_workflow_display_name,
        user_id=current_user.id,
        spec_json=default_spec_json,
        file_ids=request_body.file_ids,
        folder_id=new_workflow_folder.id,
    )
    new_workflow = create_workflow_in_db(
        db, new_workflow_db, template_id=request_body.template_id
    )
    return new_workflow


# Update workflow
@router.patch("/{workflow_id}", response_model=schemas.WorkflowResponse)
async def update_workflow(
    workflow_id: int,
    workflow_from_request: schemas.Workflow,
    db: Session = Depends(get_db_connection),
):
    # Fetch workflow to update from database
    workflow_from_db = get_workflow_from_db(db, workflow_id)
    workflow_model = schemas.Workflow(**workflow_from_db.__dict__)

    # Update workflow data with supplied values
    update_data = workflow_from_request.model_dump(exclude_unset=True)
    updated_workflow_model = workflow_model.model_copy(update=update_data)

    return update_workflow_in_db(db, updated_workflow_model)


# Copy workflow
@router.post("/{workflow_id}/copy/", response_model=schemas.WorkflowResponse)
async def copy_workflow(
    workflow_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):

    workflow_to_copy = get_workflow_from_db(db, workflow_id)
    workflow_spec = json.loads(workflow_to_copy.spec_json)
    replace_uuids(workflow_spec)

    # Create new folder for workflow results
    new_folder = schemas.FolderCreateRequest(
        display_name=f"Copy of {workflow_to_copy.display_name}",
        parent_id=workflow_to_copy.folder.parent_id,
    )
    new_workflow_folder = create_folder_in_db(db, new_folder, current_user)

    new_workflow_db = schemas.Workflow(
        display_name=f"Copy of {workflow_to_copy.display_name}",
        spec_json=json.dumps(workflow_spec),
        file_ids=[file.id for file in workflow_to_copy.files if not file.is_deleted],
        folder_id=new_workflow_folder.id,
        user_id=current_user.id,
    )
    return create_workflow_in_db(db, new_workflow_db, template_id=None)


# Delete workflow
@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(workflow_id: int, db: Session = Depends(get_db_connection)):
    delete_workflow_from_db(db, workflow_id)


# Run workflow
@router.post("/run/", response_model=schemas.WorkflowResponse)
async def run_workflow(
    request: dict,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    workflow_id = request.get("workflow_id")
    workflow_spec = request.get("workflow_spec")
    workflow_spec_json = json.dumps(workflow_spec)
    workflow = get_workflow_from_db(db, workflow_id)
    workflow.spec_json = workflow_spec_json

    input_files = [
        {
            "filename": file.display_name,
            "uuid": file.uuid.hex,
            "path": file.path,
        }
        for file in workflow.files
    ]

    output_path = workflow.folder.path
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    def get_task_signature(task_data):
        task_uuid = task_data.get("uuid", uuid4().hex)

        # Create a new DB task
        new_task_db = Task(
            display_name=task_data.get("display_name"),
            description=task_data.get("description"),
            uuid=task_uuid,
            user=current_user,
            workflow=workflow,
        )
        create_task_in_db(db, new_task_db)

        task_signature = signature(
            task_data.get("task_name"),
            kwargs={
                "input_files": input_files,
                "output_path": output_path,
                "workflow_id": workflow.id,
            },
            queue=task_data.get("queue_name"),
            task_id=task_uuid,
        )
        return task_signature

    def create_workflow(task_data):
        if task_data["type"] == "chain":
            if len(task_data["tasks"]) > 1:
                return celery_group(
                    create_workflow(task) for task in task_data["tasks"]
                )
            else:
                return celery_chain(create_workflow(task_data["tasks"][0]))
        elif task_data["type"] == "task":
            task_signature = get_task_signature(task_data)
            if task_data["tasks"]:
                if len(task_data["tasks"]) > 1:
                    return celery_chain(
                        task_signature,
                        celery_group(create_workflow(t) for t in task_data["tasks"]),
                    )
                else:
                    return celery_chain(
                        task_signature, create_workflow(task_data["tasks"][0])
                    )
            else:
                return task_signature
        else:
            raise ValueError(f"Unsupported task type: {task_data['type']}")

    celery_workflow = create_workflow(workflow_spec.get("workflow"))
    celery_workflow.apply_async()

    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    return workflow


# Get all workflow templates
@router.get("/templates/", response_model=List[schemas.WorkflowTemplateResponse])
async def get_workflow_templates(db: Session = Depends(get_db_connection)):
    return get_workflow_templates_from_db(db)


# Create workflow template
@router.post("/templates/", response_model=schemas.WorkflowTemplateResponse)
async def create_workflow_template(
    new_template_request: schemas.WorkflowTemplateCreateRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    workflow_to_save = get_workflow_from_db(db, new_template_request.workflow_id)
    # Replace UUIDs with placeholder value for the template
    spec_json = json.loads(workflow_to_save.spec_json)
    replace_uuids(spec_json, replace_with="PLACEHOLDER")

    new_template_db = schemas.WorkflowTemplateCreate(
        display_name=new_template_request.display_name,
        spec_json=json.dumps(spec_json),
        user_id=current_user.id,
    )
    return create_workflow_template_in_db(db, new_template_db)


# Get registered tasks from Celery
@router.get("/registered_tasks/")
def get_registered_tasks():
    registered_celery_tasks = celery.control.inspect().registered("metadata")
    registered_task_names = set()
    registered_tasks_formatted = []

    for _, tasks in registered_celery_tasks.items():
        for task in tasks:
            task_name = task.split()[0]
            metadata = ast.literal_eval(re.search("({.+})", task).group(0))
            if task_name in registered_task_names:
                continue
            registered_tasks_formatted.append(
                {
                    "task_name": task_name,
                    "queue_name": task_name.split(".")[0],
                    "display_name": metadata.get("display_name"),
                    "description": metadata.get("description"),
                }
            )
            registered_task_names.add(task_name)
    return registered_tasks_formatted
