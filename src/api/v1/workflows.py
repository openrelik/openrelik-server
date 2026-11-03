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

import asyncio
import functools
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from openrelik_ai_common.providers import manager
from sqlalchemy.orm import Session

from auth.common import get_current_active_user
from config import get_active_llm
from datastores.sql.crud.authz import (
    check_user_access,
    get_workflow_with_access,
    require_access,
)
from datastores.sql.crud.file import get_file_from_db
from datastores.sql.crud.folder import create_subfolder_in_db
from datastores.sql.crud.workflow import (
    create_workflow_in_db,
    create_workflow_template_in_db,
    delete_workflow_template_from_db,
    delete_workflow_from_db,
    get_folder_workflows_from_db,
    get_workflow_template_from_db,
    get_workflow_templates_from_db,
    update_workflow_in_db,
    update_workflow_template_in_db,
)
from datastores.sql.database import get_db_connection
from datastores.sql.models.role import Role
from lib import workflow_utils
from lib.reporting_utils import create_workflow_report
from lib.workflow_utils import TemplateNotFoundError, replace_uuids

from . import schemas

VIEW_ROLES = [Role.VIEWER, Role.EDITOR, Role.OWNER]
EDIT_ROLES = [Role.EDITOR, Role.OWNER]

# Fields of a workflow that clients can change with PATCH. The others, like folder_id and
# user_id, decide where the workflow lives and who owns it, so they can't be set this way.
UPDATABLE_WORKFLOW_FIELDS = {"display_name", "description", "spec_json"}


def _check_file_access(db: Session, current_user: schemas.User, file_ids: List[int]) -> None:
    """Check that the user can view every file in file_ids.

    Raises:
        HTTPException: 404 if a file doesn't exist or is deleted, 403 if the user has no access.
    """
    for file_id in file_ids:
        file = get_file_from_db(db, file_id)
        if not file or file.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"File {file_id} not found."
            )
        if not check_user_access(db, current_user, VIEW_ROLES, file=file):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"No access to file {file_id}"
            )


# Workflows in a folder context.
router = APIRouter()

# Router for resources that live under /workflows, i.e. outside of a folder context.
router_root = APIRouter()


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
    _check_file_access(db, current_user, request_body.file_ids)
    try:
        return workflow_utils.create_workflow(
            db,
            folder_id=folder_id,
            file_ids=request_body.file_ids,
            template_id=request_body.template_id,
            template_params=request_body.template_params,
            user=current_user,
        )
    except TemplateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


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
    return get_workflow_with_access(db, current_user, workflow_id, VIEW_ROLES)


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
    workflow_from_db = get_workflow_with_access(db, current_user, workflow_id, EDIT_ROLES)
    workflow_model = schemas.Workflow(**workflow_from_db.__dict__)

    # Update workflow data with supplied values
    update_data = {
        key: value
        for key, value in workflow_from_request.model_dump(exclude_unset=True).items()
        if key in UPDATABLE_WORKFLOW_FIELDS
    }
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

    workflow_to_copy = get_workflow_with_access(db, current_user, workflow_id, EDIT_ROLES)
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
    get_workflow_with_access(db, current_user, workflow_id, EDIT_ROLES)
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
    workflow = get_workflow_with_access(db, current_user, workflow_id, EDIT_ROLES)
    return workflow_utils.run_workflow(
        db,
        workflow=workflow,
        workflow_spec=request_body.workflow_spec,
        user=current_user,
    )


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
    workflow = get_workflow_with_access(db, current_user, workflow_id, VIEW_ROLES)

    # Terminal task states where a task is considered finished
    TERMINAL_TASK_STATES = {"SUCCESS", "FAILURE", "REVOKED", "REJECTED"}
    FAILED_TASK_STATES = {"FAILURE", "REJECTED"}

    has_any_tasks = False
    has_failed_tasks = False
    has_non_terminal_tasks = False

    for task in workflow.tasks:
        has_any_tasks = True
        if task.status_short in FAILED_TASK_STATES:
            has_failed_tasks = True
        if task.status_short not in TERMINAL_TASK_STATES:
            has_non_terminal_tasks = True

    # Logic for determining workflow status
    if not has_any_tasks:
        workflow_status = "PENDING"  # Explicitly set to PENDING if no tasks
    elif has_non_terminal_tasks:
        workflow_status = "RUNNING"
    elif has_failed_tasks:
        workflow_status = "COMPLETE_WITH_FAILURES"
    else:
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
        workflow_to_save = get_workflow_with_access(
            db, current_user, request_body.workflow_id, VIEW_ROLES
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


def _check_can_delete_workflow_template(
    db: Session, template_id: int, current_user: schemas.User
) -> None:
    """Check that the current user is allowed to delete a workflow template.

    The creator of a template can delete it. Admins can delete any template,
    including orphaned ones whose creator no longer exists.

    Raises:
        HTTPException: 404 if the template does not exist, 403 if the user is
            neither its creator nor an admin.
    """
    template = get_workflow_template_from_db(db, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow template {template_id} not found",
        )
    if template.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the creator of a workflow template or an admin can delete it.",
        )


# Update workflow template
# /workflows/templates/{template_id}
@router_root.patch("/templates/{template_id}")
async def update_workflow_template(
    template_id: int,
    request_body: schemas.WorkflowTemplateUpdateRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowTemplateResponse:
    """Update a workflow template's name or description. Any user can; only
    deleting is restricted to its creator or an admin.

    The description can be cleared by sending null or an empty string. The
    display name cannot be empty.

    WorkflowTemplateUpdateRequest (request_body):
        - display_name (Optional[str]): The display name of the template.
        - description (Optional[str]): The description of the template.

    Args:
        template_id (int): The ID of the template to update.
        request_body (schemas.WorkflowTemplateUpdateRequest): The fields to update.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        schemas.WorkflowTemplateResponse: The updated workflow template.
    """
    if not get_workflow_template_from_db(db, template_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow template {template_id} not found",
        )
    fields = request_body.model_dump(exclude_unset=True)
    if "display_name" in fields and not (fields["display_name"] or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="display_name cannot be empty.",
        )
    update = schemas.WorkflowTemplateUpdate(id=template_id, **fields)
    return update_workflow_template_in_db(db, update)


# Delete workflow template
# /workflows/templates/{template_id}
@router_root.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_template(
    template_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Delete a workflow template. Only its creator or an admin can.

    Workflows created from it are kept.

    Args:
        template_id (int): The ID of the template to delete.
        db (Session): The database session.
        current_user (schemas.User): The current user.
    """
    _check_can_delete_workflow_template(db, template_id, current_user)
    delete_workflow_template_from_db(db, template_id)


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
    workflow = get_workflow_with_access(db, current_user, workflow_id, EDIT_ROLES)
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
    active_llm = get_active_llm()
    if not active_llm:
        raise HTTPException(
            status_code=503,
            detail="No active LLM available.",
        )
    provider = manager.LLMManager().get_provider(active_llm["name"])
    llm = provider(model_name=active_llm["config"]["model"])
    loop = asyncio.get_running_loop()
    generated_name = await loop.run_in_executor(
        None, functools.partial(llm.generate, prompt=prompt)
    )
    # Limit the generated name to a maximum number of MAX_WORDS
    generated_name = " ".join(generated_name.split()[:MAX_WORDS])
    return {"generated_name": generated_name.strip()}


# Get workflow
# /workflows/{workflow_id}
@router_root.get("/{workflow_id}")
async def get_workflow(
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
        workflow_id (int): The ID of the workflow to get.
        db (Session): The database session.
        current_user (schemas.User): The current user.

    Returns:
        schemas.WorkflowResponse: The workflow.
    """
    return get_workflow_with_access(db, current_user, workflow_id, VIEW_ROLES)

# Generate workflow report
# /workflows/{workflow_id}/report
@router_root.get("/{workflow_id}/report/")
async def generate_workflow_report(
    workflow_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.WorkflowReportResponse:
    workflow = get_workflow_with_access(db, current_user, workflow_id, EDIT_ROLES)

    markdown = create_workflow_report(workflow)
    response = schemas.WorkflowReportResponse(
        workflow=workflow,
        markdown=markdown,
    )
    return response

