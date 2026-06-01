# Copyright 2026 Google LLC
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

"""Workflow helpers to create, manipulate or run workflows."""

import json
import os
from typing import Optional
from uuid import uuid4

from celery import chain as celery_chain
from celery import chord as celery_chord
from celery import group as celery_group
from celery import signature
from celery.app import Celery
from celery.canvas import Signature
from sqlalchemy.orm import Session

from api.v1 import schemas
from datastores.sql.crud.folder import create_subfolder_in_db
from datastores.sql.crud.workflow import (
    create_task_in_db,
    create_workflow_in_db,
    get_workflow_template_from_db,
)
from datastores.sql.models.workflow import Task, Workflow

# Redis URL and Celery app initialization.
_redis_url = os.getenv("REDIS_URL")
celery_app = Celery(broker=_redis_url, backend=_redis_url)


def update_task_config_values(data: dict | list, parameters: dict) -> None:
    """
    Recursively traverses a dictionary or list to find 'task_config' lists
    and updates the 'value' of each item based on the unique 'param_name'.

    Args:
        data (dict | list): The dictionary or list to traverse.
        parameters (dict): A dictionary where keys are the unique 'param_name'.
    """
    if isinstance(data, dict):
        task_config = data.get("task_config", [])
        for item in task_config:
            param_name = item.get("param_name")
            if not param_name:
                continue

            if param_name in parameters:
                item["value"] = parameters[param_name]
                continue

        for _, value in data.items():
            update_task_config_values(value, parameters)

    elif isinstance(data, list):
        for item in data:
            update_task_config_values(item, parameters)


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
            create_workflow_signature(
                db, current_user, t, input_files, output_path, workflow
            )
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


class TemplateNotFoundError(ValueError):
    """Raised when ``create_workflow`` cannot resolve a template id."""


def create_workflow(
    db: Session,
    *,
    display_name: Optional[str] = None,
    folder_id: int,
    file_ids: list[int],
    template_id: Optional[int],
    template_params: Optional[dict],
    user: schemas.User,
) -> Workflow:
    """Create a Workflow (optionally from a template) and return it.

    Args:
        db (Session): The database session.
        display_name (Optional[str]): Optional override for the workflow's
            (and results subfolder's) display name. When None, falls back to
            the template's display name, or "Untitled workflow" if no
            template.
        folder_id (int): The ID of the parent folder that will hold the
            workflow's results subfolder.
        file_ids (list[int]): IDs of the files to associate with the workflow.
        template_id (Optional[int]): Optional ID of a workflow template to
            create the workflow from.
        template_params (Optional[dict]): Optional dict of parameter values
            to apply to the template's task configs. Keys should correspond
            to the template's task config parameters.
        user (schemas.User): The user creating the workflow.

    Returns:
        Workflow: The newly created workflow.

    Raises:
        TemplateNotFoundError: When ``template_id`` is provided but the
            template does not exist.
    """
    default_workflow_display_name = "Untitled workflow"
    default_spec_json = None
    from_template = None

    if template_id:
        from_template = get_workflow_template_from_db(db, template_id)
        if not from_template:
            raise TemplateNotFoundError(f"Workflow template {template_id} not found")
        default_workflow_display_name = from_template.display_name
        spec_json = json.loads(from_template.spec_json)
        # Replace the placeholder UUIDs seeded in the template with fresh ones
        # so each workflow instance has unique identifiers.
        replace_uuids(spec_json)
        if template_params:
            update_task_config_values(spec_json, template_params)
        default_spec_json = json.dumps(spec_json)

    workflow_display_name = display_name or default_workflow_display_name

    # Create a new folder to hold workflow results.
    new_folder = schemas.FolderCreateRequest(
        display_name=workflow_display_name, parent_id=folder_id
    )
    new_workflow_folder = create_subfolder_in_db(db, folder_id, new_folder, user)

    new_workflow_db = schemas.Workflow(
        display_name=workflow_display_name,
        user_id=user.id,
        spec_json=default_spec_json,
        file_ids=file_ids,
        folder_id=new_workflow_folder.id,
        template_id=from_template.id if from_template else None,
    )
    return create_workflow_in_db(db, new_workflow_db)


def run_workflow(
    db: Session,
    *,
    workflow: Workflow,
    workflow_spec: dict,
    user: schemas.User,
) -> Workflow:
    """Runs a workflow via Celery.

    Builds input-file dicts from ``workflow.files``, ensures the output
    directory exists, constructs the Celery canvas, and calls
    ``apply_async()``.

    Returns:
        A Workflow instance representing the workflow that was run.
    """
    workflow.spec_json = json.dumps(workflow_spec)

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
        user,
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
