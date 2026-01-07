# Copyright 2024-2026 Google LLC
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
from celery import chord as celery_chord
from celery import group as celery_group
from celery import signature
from celery.app import Celery
from celery.canvas import Signature
from fastapi import APIRouter, Depends, HTTPException, status
from openrelik_ai_common.providers import manager
from sqlalchemy.orm import Session

from auth.common import get_current_active_user
from config import get_active_llms
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
    update_workflow_template_in_db,
)
from datastores.sql.database import get_db_connection
from datastores.sql.models.role import Role
from datastores.sql.models.workflow import Task
from lib import workflow_utils
from lib.reporting_utils import create_workflow_report

from . import schemas

redis_url = os.getenv("REDIS_URL")
celery = Celery(broker=redis_url, backend=redis_url)

# Workflows in a folder context.
router = APIRouter()

# Router for resources that live under /workflows, i.e. outside of a folder context.
router_root = APIRouter()


def get_task_signature(
    db: Session,
    current_user: schemas.User,
    task_data: dict,
    input_files: list,
    output_path: str,
    workflow: schemas.Workflow,
) -> Signature:
    """Returns a Celery task signature for a given task.

    Args:
        db (Session): The database session.
        current_user (schemas.User): The current user.
        task_data (dict): The task data.
        input_files (list): A list of input files.
        output_path (str): The output path.
        workflow (schemas.Workflow): The workflow.

    Returns:
        Signature: The Celery task signature.
    """
    task_uuid = task_data.get("uuid", uuid4().hex)
    task_config = {
        option["name"]: option.get("value") for option in task_data.get("task_config", {})
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


def create_workflow_signature(
    db: Session,
    current_user: schemas.User,
    task_data: dict,
    input_files: list,
    output_path: str,
    workflow: schemas.Workflow,
) -> Signature:
    """Creates a Celery workflow signature for a given task definition

    This function recursively constructs a Celery workflow signature based on the
    provided `task_data`, which represents a structured description of tasks and their
    dependencies. It supports two primary task types: 'chain' and 'task'.

    chain: Represents a sequence of tasks executed in order.
        -   If the chain contains multiple tasks, a Celery `celery_group` is created to
            execute them concurrently. celery_group allows multiple tasks to be run
            in parallel.
        -   If only one task is present, a Celery `celery_chain` is created to execute
            it *serially*. `celery_chain` ensures tasks are executed one after another,
            ith the output of one task becoming the input of the next.

    task: Represents a single, executable task.
        - It retrieves the corresponding Celery task signature using get_task_signature.
        - If the task has sub-tasks, they are incorporated into the workflow using
          Celery `celery_chain` and `celery_group` constructs, depending on the number
          of sub-tasks. The primary task is chained with the subtasks.

    The function effectively translates a hierarchical task description into a Celery
    workflow that can be executed asynchronously. This allows for complex workflows to
    be defined and executed in a distributed manner.

    Args:
        db (Session): The database session.
        current_user (schemas.User): The current user.
        task_data (dict): The task data.
        input_files (list): A list of input files.
        output_path (str): The output path.
        workflow (schemas.Workflow): The workflow.

    Returns:
        Signature: The Celery workflow signature.

    Raises:
        ValueError: If the task type is not supported.
    """
    if task_data["type"] == "chain":
        if len(task_data["tasks"]) > 1:
            return celery_group(
                create_workflow_signature(
                    db, current_user, task, input_files, output_path, workflow
                )
                for task in task_data["tasks"]
            )
        else:
            return celery_chain(
                create_workflow_signature(
                    db,
                    current_user,
                    task_data["tasks"][0],
                    input_files,
                    output_path,
                    workflow,
                )
            )

    elif task_data["type"] == "chord":
        header_tasks = [
            create_workflow_signature(db, current_user, t, input_files, output_path, workflow)
            for t in task_data.get("tasks", [])
        ]

        callback_task_data = task_data.get("callback")
        if not callback_task_data:
            raise ValueError("Chord definition requires a 'callback' task.")

        callback_signature = create_workflow_signature(
            db, current_user, callback_task_data, input_files, output_path, workflow
        )

        return celery_chord(header_tasks, callback_signature)

    elif task_data["type"] == "task":
        task_signature = get_task_signature(
            db, current_user, task_data, input_files, output_path, workflow
        )
        if task_data["tasks"]:
            if len(task_data["tasks"]) > 1:
                return celery_chain(
                    task_signature,
                    celery_group(
                        create_workflow_signature(
                            db, current_user, t, input_files, output_path, workflow
                        )
                        for t in task_data["tasks"]
                    ),
                )
            else:
                return celery_chain(
                    task_signature,
                    create_workflow_signature(
                        db,
                        current_user,
                        task_data["tasks"][0],
                        input_files,
                        output_path,
                        workflow,
                    ),
                )
        else:
            return task_signature
    else:
        raise ValueError(f"Unsupported task type: {task_data['type']}")


def replace_uuids(data: dict | list, replace_with: str = None) -> dict | list:
    """Recursively replaces UUID keys within a dictionary or list structure.

    This function traverses the provided `data` structure (which can be a dictionary or
    list) and replaces any dictionary keys named "uuid" with a new value.

    If `replace_with` is not provided (or is None), a newly generated UUID is used as
    the replacement. If `replace_with` is provided, that value is used as the
    replacement for all "uuid" keys.

    This is needed when modifying workflow specifications that contain UUIDs, ensuring
    that each instance has unique identifiers.

    Args:
        data (dict | list): The dictionary or list to traverse and modify.
        replace_with (str, optional): The value to replace UUIDs with. Defaults to None.

    Returns:
        dict | list: The modified dictionary or list with UUIDs replaced.
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
    """Create a new workflow.

    WorkflowCreateRequest (request_body):
        - folder_id (int): The ID of the folder where the workflow will be created.
        - file_ids (List[int]): A list of file IDs associated with the workflow.
        - template_id (Optional[int]): The ID of a workflow template to use. If provided,
        the workflow will be created based on the template.
        - template_params (Optional[dict]): A dictionary of parameters to customize the paramters
            of the workflow template.

    Args:
        folder_id (int): The ID of the folder to create the workflow in.
        request_body (schemas.WorkflowCreateRequest): The request body to create the workflow.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        schemas.WorkflowResponse: The created workflow.
    """
    default_workflow_display_name = "Untitled workflow"
    default_spec_json = None

    from_template = None

    if request_body.template_id:
        from_template = get_workflow_template_from_db(db, request_body.template_id)
        default_workflow_display_name = from_template.display_name
        spec_json = json.loads(from_template.spec_json)
        # Replace UUIDs with placeholder value for the template
        replace_uuids(spec_json)
        # Add parameter values to task_config items
        if request_body.template_params:
            workflow_utils.update_task_config_values(spec_json, request_body.template_params)

        default_spec_json = json.dumps(spec_json)

    # Create new folder for workflow results
    new_folder = schemas.FolderCreateRequest(
        display_name=default_workflow_display_name, parent_id=request_body.folder_id
    )
    new_workflow_folder = create_subfolder_in_db(db, folder_id, new_folder, current_user)

    # Create new workflow
    new_workflow_db = schemas.Workflow(
        display_name=default_workflow_display_name,
        user_id=current_user.id,
        spec_json=default_spec_json,
        file_ids=request_body.file_ids,
        folder_id=new_workflow_folder.id,
        template_id=from_template.id if from_template else None,
    )
    new_workflow = create_workflow_in_db(db, new_workflow_db)
    return new_workflow


# Get all workflows for a folder
# /folders/{folder_id}/workflows
@router.get("/workflows")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_workflows(
    folder_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.WorkflowResponse]:
    """Get all workflows for a folder.

    WorkflowResponse:
        - id (int): The ID of the workflow.
        - display_name (str): The display name of the workflow.
        - spec_json (str): The JSON representation of the workflow specification.
        - file_ids (List[int]): A list of file IDs associated with the workflow.
        - folder_id (int): The ID of the folder the workflow belongs to.
        - user_id (int): The ID of the user who created the workflow.
        - created_at (datetime): The timestamp when the workflow was created.
        - updated_at (datetime): The timestamp when the workflow was last updated.

    Args:
        folder_id (int): The ID of the folder to get workflows for.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        List[schemas.WorkflowResponse]: A list of workflows
    """
    return get_folder_workflows_from_db(db, folder_id)


# Get workflow
# /folders/{folder_id}/workflows/{workflow_id}
@router.get("/{workflow_id}")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
async def get_workflow(
    folder_id: int,
    workflow_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowResponse:
    """Get a workflow by ID.

    WorkflowResponse:
        - id (int): The ID of the workflow.
        - display_name (str): The display name of the workflow.
        - spec_json (str): The JSON representation of the workflow specification.
        - file_ids (List[int]): A list of file IDs associated with the workflow.
        - folder_id (int): The ID of the folder the workflow belongs to.
        - user_id (int): The ID of the user who created the workflow.
        - created_at (datetime): The timestamp when the workflow was created.
        - updated_at (datetime): The timestamp when the workflow was last updated.

    Args:
        folder_id (int): The ID of the folder the workflow belongs to.
        workflow_id (int): The ID of the workflow to get.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        schemas.WorkflowResponse: The workflow.
    """
    return get_workflow_from_db(db, workflow_id)


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
    """Update a workflow by ID.

    Workflow (workflow_from_request):
        - display_name (str): The display name of the workflow.
        - description (Optional[str]): The description of the workflow.
        - spec_json (Optional[str]): JSON representation of the workflow specification.
        - uuid (Optional[UUID]): The UUID of the workflow.
        - user_id (int): The ID of the user who created the workflow.
        - file_ids (List[int]): A list of file IDs associated with the workflow.
        - folder_id (int): The ID of the folder the workflow belongs to.

    Args:
        folder_id (int): The ID of the folder the workflow belongs to.
        workflow_id (int): The ID of the workflow to update.
        workflow_from_request (schemas.Workflow): The updated workflow data.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        schemas.WorkflowResponse: The updated workflow.
    """

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
    """Copy a workflow.

    Args:
        folder_id (int): The ID of the folder to copy the workflow to.
        workflow_id (int): The ID of the workflow to copy.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        schemas.WorkflowResponse: The copied workflow.
    """

    workflow_to_copy = get_workflow_from_db(db, workflow_id)
    workflow_spec = json.loads(workflow_to_copy.spec_json)
    replace_uuids(workflow_spec)

    # Create new folder for workflow results
    new_folder = schemas.FolderCreateRequest(
        display_name=f"Copy of {workflow_to_copy.display_name}",
    )
    new_workflow_folder = create_subfolder_in_db(
        db,
        folder_id=workflow_to_copy.folder.parent_id,
        new_folder=new_folder,
        current_user=current_user,
    )

    new_workflow_db = schemas.Workflow(
        display_name=f"Copy of {workflow_to_copy.display_name}",
        spec_json=json.dumps(workflow_spec),
        file_ids=[file.id for file in workflow_to_copy.files if not file.is_deleted],
        folder_id=new_workflow_folder.id,
        user_id=current_user.id,
    )
    return create_workflow_in_db(db, new_workflow_db)


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
    """Delete a workflow by ID.

    Args:
        folder_id (int): The ID of the folder the workflow belongs to.
        workflow_id (int): The ID of the workflow to delete.
        db (Session): The database session.
        current_user (schemas.User): The current user.
    """
    delete_workflow_from_db(db, workflow_id)


# Run workflow
# /folders/{folder_id}/workflows/{workflow_id}/run
@router.post("/{workflow_id}/run/")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def run_workflow(
    folder_id: int,
    workflow_id: int,
    request_body: schemas.WorkflowRunRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowResponse:
    """Run a workflow.

    WorkflowRunRequest (request_body):
        - workflow_spec (dict): The workflow specification.

    Args:
        folder_id (int): The ID of the folder the workflow belongs to.
        workflow_id (int): The ID of the workflow to run.
        request_body (schemas.WorkflowRunRequest): The request body to run the workflow.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        schemas.WorkflowResponse: The workflow.
    """
    workflow_spec = request_body.workflow_spec
    workflow_spec_json = json.dumps(workflow_spec)
    workflow = get_workflow_from_db(db, workflow_id)
    # Update workflow spec
    workflow.spec_json = workflow_spec_json

    input_files = [
        {
            "id": file.id,
            "uuid": file.uuid.hex,
            "display_name": file.display_name,
            "extension": file.extension,
            "data_type": file.data_type,
            "mime_type": file.magic_mime,
            "path": file.path,
        }
        for file in workflow.files
    ]

    output_path = workflow.folder.path
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    celery_workflow = create_workflow_signature(
        db,
        current_user,
        workflow_spec.get("workflow"),
        input_files,
        output_path,
        workflow,
    )
    celery_workflow.apply_async()

    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    return workflow


# Get workflow status
# /folders/{folder_id}/workflows/{workflow_id}/status
@router.get("/{workflow_id}/status")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
async def get_workflow_status(
    folder_id: int,
    workflow_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowStatus:
    """Get a workflow status by ID."""
    workflow = get_workflow_from_db(db, workflow_id)
    workflow_status = "PENDING"

    # Flags to track different task statuses
    has_running_tasks = False
    has_failed_tasks = False
    has_any_tasks = False

    for task in workflow.tasks:
        has_any_tasks = True
        if task.status_short in ["STARTED", "PROGRESS", "RECEIVED"]:
            has_running_tasks = True
        elif task.status_short == "FAILURE":
            has_failed_tasks = True

    # Logic for determining workflow status
    if not has_any_tasks:
        workflow_status = "PENDING"  # Explicitly set to PENDING if no tasks
    elif has_running_tasks:
        workflow_status = "RUNNING"
    elif has_failed_tasks:
        workflow_status = "COMPLETE_WITH_FAILURES"
    else:
        # If there are tasks, but none are running or failed, then it's complete
        workflow_status = "COMPLETE"

    return {
        "status": workflow_status,
        "tasks": workflow.tasks,
    }


# Get all workflow templates
# /workflows/templates
@router_root.get("/templates/")
async def get_workflow_templates(
    db: Session = Depends(get_db_connection),
) -> List[schemas.WorkflowTemplateResponse]:
    """Get all workflow templates.

    Args:
        db (Session): The database session.

    Returns:
        List[schemas.WorkflowTemplateResponse]: A list of workflow templates.
    """
    return get_workflow_templates_from_db(db)


# Get workflow template by id
# /workflows/templates/id
@router_root.get("/templates/{template_id}")
async def get_workflow_template_by_id(
    template_id: int,
    db: Session = Depends(get_db_connection),
) -> schemas.WorkflowTemplateResponse:
    """Get workflow template by id.

    Args:
        template_id (int): The ID of the template.
        db (Session): The database session.

    Returns:
        schemas.WorkflowTemplateResponse: A workflow template.
    """
    return get_workflow_template_from_db(db, template_id)


# Create workflow template
# /workflows/templates
@router_root.post("/templates/")
async def create_workflow_template(
    request_body: schemas.WorkflowTemplateCreateRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowTemplateResponse:
    """Create a new workflow template.

    WorkflowTemplateCreateRequest (request_body):
        - display_name (str): The display name of the template.
        - description (Optional[str]): The description of the template.
        - workflow_id (Optional[int]): The ID of the workflow to create the template from.

    Args:
        request_body (schemas.WorkflowTemplateCreateRequest): The request body to create the template.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        schemas.WorkflowTemplateResponse: The created workflow template.
    """
    spec_json = None
    if request_body.workflow_id:
        workflow_to_save = get_workflow_from_db(db, request_body.workflow_id)
        if not workflow_to_save:
            raise HTTPException(
                status_code=404,
                detail="Workflow with id {new_template_request.workflow_id} not found",
            )

        # Replace UUIDs with placeholder value for the template
        spec_json = json.loads(workflow_to_save.spec_json)
        replace_uuids(spec_json, replace_with="PLACEHOLDER")

    new_template_db = schemas.WorkflowTemplateCreate(
        display_name=request_body.display_name,
        spec_json=json.dumps(spec_json),
        user_id=current_user.id,
    )
    return create_workflow_template_in_db(db, new_template_db)


# Update workflow template
# /workflows/templates/{template_id}
@router_root.patch("/templates/{template_id}")
async def update_workflow_template(
    template_id: int,
    template_from_request: schemas.WorkflowTemplateResponse,
    db: Session = Depends(get_db_connection),
) -> schemas.WorkflowTemplateResponse:
    """Update a workflow template.

    WorkflowTemplateReponse (template_from_request):
        - display_name (str): The display name of the template.
        - description (Optional[str]): The description of the template.
        - spec_json (Optional[str]): JSON representation of the workflow specification.

    Args:
        template_id (int): The ID of the template to update.
        template_from_request (schemas.WorkflowTemplateCreateRequest): The template data to update.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        schemas.WorkflowTemplateResponse: The created workflow template.
    """
    # Fetch workflow to update from database
    template_from_db = get_workflow_template_from_db(db, template_id)
    template_model = schemas.WorkflowTemplateCreate(**template_from_db.__dict__)

    # Update template data with supplied values
    update_data = template_from_request.model_dump(exclude_unset=True)
    updated_template_model = template_model.model_copy(update=update_data)

    return update_workflow_template_in_db(db, updated_template_model)


# Generate workflow name
# /folders/{folder_id}/workflows/{workflow_id}
@router.get("/{workflow_id}/generate_name/")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def generate_workflow_name(
    folder_id: int,
    workflow_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowGeneratedNameResponse:
    """Generate a name for a workflow.
    This endpoint generates a concise name for a workflow based on its JSON representation
    and input filenames. The generated name is intended to be descriptive and reflect the
    purpose of the workflow.
    The name is generated using a language model.

    Args:
        folder_id (int): The ID of the folder the workflow belongs to.
        workflow_id (int): The ID of the workflow to generate a name for.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        schemas.WorkflowGeneratedNameResponse: The generated workflow name.
    """
    workflow = get_workflow_from_db(db, workflow_id)
    MAX_WORDS = 5

    def _remove_task_config(data: dict | list) -> dict | list:
        """Recursively removes 'task_config' keys from the workflow spec."""
        if isinstance(data, dict):
            new_data = {}
            for key, value in data.items():
                if key == "task_config":
                    continue
                else:
                    new_data[key] = _remove_task_config(value)
            return new_data
        elif isinstance(data, list):
            return [_remove_task_config(item) for item in data]
        else:
            return data

    workflow_spec = _remove_task_config(json.loads(workflow.spec_json))
    prompt = f"""
    Generate a concise (3-5 words) title for a workflow based on its WORKFLOW_JSON representation
    and input FILENAMES_WITH_FILETYPES.
    * FILENAME_WITH_FILETYPES has the form of [(filename, filetype)]
    * Focus on summarizing the main actions and data processed.
    * The name should be descriptive and reflect the purpose of the workflow.
    * The name should be in English and no more than {MAX_WORDS} words long.
    * The name should be in title case.
    * The name should NOT include any special characters or numbers.
    * The name should NOT include the word 'workflow'.
    * The name should NOT be formatted'.

    Good examples:
    * Evtx Timeline And Report
    * PDF Text Extraction
    * Evtx Triage And Timeline

    WORKFLOW_JSON:
    {json.dumps(workflow_spec)}

    Input FILENAMES_WITH_FILETYPES:
    {", ".join([f"({file.display_name}, {file.magic_mime})" for file in workflow.files])}
    """
    active_llm = get_active_llms()[0]
    if not active_llm:
        raise HTTPException(
            status_code=503,
            detail="No active LLM available.",
        )
    provider = manager.LLMManager().get_provider(active_llm["name"])
    llm = provider(model_name=active_llm["config"]["model"])
    generated_name = llm.generate(prompt=prompt)
    # Limit the generated name to a maximum number of MAX_WORDS
    generated_name = " ".join(generated_name.split()[:MAX_WORDS])
    return {"generated_name": generated_name.strip()}


# Generate workflow report
# /workflows/{workflow_id}/report
@router_root.get("/{workflow_id}/report/")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def generate_workflow_report(
    workflow_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowReportResponse:
    workflow = get_workflow_from_db(db, workflow_id)
    markdown = create_workflow_report(workflow)
    response = schemas.WorkflowReportResponse(
        workflow=workflow,
        markdown=markdown,
    )
    return response
