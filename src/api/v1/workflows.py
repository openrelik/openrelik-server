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

import json
import os
from typing import List
from uuid import uuid4

from celery import chain as celery_chain
from celery import group as celery_group
from celery import signature
from celery.app import Celery
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from auth.common import get_current_active_user
from datastores.sql.crud.authz import require_access
from datastores.sql.crud.folder import create_subfolder_in_db
from datastores.sql.crud.workflow import (
    create_task_in_db,
    create_workflow_in_db,
    create_workflow_template_in_db,
    delete_workflow_from_db,
    get_folder_workflows_from_db,
    get_workflow_from_db,
    get_workflow_template_from_db,
    get_workflow_templates_from_db,
    update_workflow_in_db,
)
from datastores.sql.database import get_db_connection
from datastores.sql.models.workflow import Task
from datastores.sql.models.role import Role

from . import schemas

redis_url = os.getenv("REDIS_URL")
celery = Celery(broker=redis_url, backend=redis_url)

# Workflows in a folder context.
router = APIRouter()

# Router for resouces that live under /workflows, i.e. outside of a folder context.
router_root = APIRouter()


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


# Create workflow
# /folders/{folder_id}/workflows
@router.post("/")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def create_workflow(
    folder_id: int,
    request_body: schemas.WorkflowCreateRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowResponse:

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
    new_workflow_folder = create_subfolder_in_db(
        db, folder_id, new_folder, current_user
    )

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


# Get workflow
# /folders/{folder_id}/workflows/{workflow_id}
@router.get("/{workflow_id}")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
async def get_workflow(
    workflow_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowResponse:
    return get_workflow_from_db(db, workflow_id)


# Get all workflows for a folder
@router.get("/workflows")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_workflows(
    folder_id: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.WorkflowResponse]:
    return get_folder_workflows_from_db(db, folder_id)


# Update workflow
# /folders/{folder_id}/workflows/{workflow_id}
@router.patch("/{workflow_id}")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def update_workflow(
    folder_id: int,
    workflow_id: int,
    workflow_from_request: schemas.Workflow,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowResponse:
    # Fetch workflow to update from database
    workflow_from_db = get_workflow_from_db(db, workflow_id)
    workflow_model = schemas.Workflow(**workflow_from_db.__dict__)

    # Update workflow data with supplied values
    update_data = workflow_from_request.model_dump(exclude_unset=True)
    updated_workflow_model = workflow_model.model_copy(update=update_data)

    return update_workflow_in_db(db, updated_workflow_model)


# Copy workflow
# /folders/{folder_id}/workflows/{workflow_id}/copy
@router.post("/{workflow_id}/copy/")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def copy_workflow(
    folder_id: int,
    workflow_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowResponse:

    workflow_to_copy = get_workflow_from_db(db, workflow_id)
    workflow_spec = json.loads(workflow_to_copy.spec_json)
    replace_uuids(workflow_spec)

    # Create new folder for workflow results
    new_folder = schemas.FolderCreateRequest(
        display_name=f"Copy of {workflow_to_copy.display_name}",
        parent_id=workflow_to_copy.folder.parent_id,
    )
    new_workflow_folder = create_subfolder_in_db(
        db, folder_id, new_folder, current_user
    )

    new_workflow_db = schemas.Workflow(
        display_name=f"Copy of {workflow_to_copy.display_name}",
        spec_json=json.dumps(workflow_spec),
        file_ids=[file.id for file in workflow_to_copy.files if not file.is_deleted],
        folder_id=new_workflow_folder.id,
        user_id=current_user.id,
    )
    return create_workflow_in_db(db, new_workflow_db, template_id=None)


# Delete workflow
# /folders/{folder_id}/workflows/{workflow_id}
@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def delete_workflow(
    folder_id: int,
    workflow_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    delete_workflow_from_db(db, workflow_id)


# Run workflow
# /folders/{folder_id}/workflows/{workflow_id}/run
@router.post("/{workflow_id}/run/")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def run_workflow(
    folder_id: int,
    workflow_id: int,
    request: dict,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowResponse:
    workflow_spec = request.get("workflow_spec")
    workflow_spec_json = json.dumps(workflow_spec)
    workflow = get_workflow_from_db(db, workflow_id)
    workflow.spec_json = workflow_spec_json

    input_files = [
        {
            "id": file.id,
            "uuid": file.uuid.hex,
            "display_name": file.display_name,
            "extension": file.extension,
            "data_type": file.data_type,
            "path": file.path,
        }
        for file in workflow.files
    ]

    output_path = workflow.folder.path
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    def get_task_signature(task_data):
        task_uuid = task_data.get("uuid", uuid4().hex)
        task_config = {
            option["name"]: option.get("value")
            for option in task_data.get("task_config", {})
        }

        # Create a new DB task
        new_task_db = Task(
            display_name=task_data.get("display_name"),
            description=task_data.get("description"),
            config=json.dumps(task_config),
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
                "task_config": task_config,
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


### Root level resources (/workflows/...)


# Get all workflow templates
# /workflows/templates
@router_root.get("/templates/")
async def get_workflow_templates(
    db: Session = Depends(get_db_connection),
) -> List[schemas.WorkflowTemplateResponse]:
    return get_workflow_templates_from_db(db)


# Create workflow template
# /workflows/templates
@router_root.post("/templates/")
async def create_workflow_template(
    new_template_request: schemas.WorkflowTemplateCreateRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowTemplateResponse:
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
