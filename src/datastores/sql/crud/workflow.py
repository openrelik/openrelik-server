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

import uuid

from sqlalchemy.orm import Session

from datastores.sql.models.workflow import Workflow, Task, WorkflowTemplate
from api.v1 import schemas

from datastores.sql.crud.file import get_file_from_db


def get_file_workflows_from_db(db: Session, file_id: int):
    """Get all workflows for a file.

    Args:
        db (Session): SQLAlchemy session object
        file_id (int): ID of the file

    Returns:
        List of Workflow objects
    """
    file = get_file_from_db(db, file_id)
    return file.workflows


def get_folder_workflows_from_db(db: Session, folder_id: int):
    """Get all workflows for a folder.

    Args:
        db (Session): SQLAlchemy session object
        folder_id (int): ID of the folder

    Returns:
        List of Workflow objects
    """
    workflows = (
        db.query(Workflow).filter_by(folder_id=folder_id).order_by(Workflow.id.desc())
    ).all()
    return workflows


def get_workflow_from_db(db: Session, workflow_id: int):
    """Get a workflow by ID.

    Args:
        db (Session): SQLAlchemy session object
        workflow_id (int): ID of the workflow

    Returns:
        Workflow object
    """
    return db.get(Workflow, workflow_id)


def create_workflow_in_db(db: Session, workflow: schemas.Workflow, template_id: int):
    """Create a new workflow.

    Args:
        db (Session): SQLAlchemy session object
        workflow (Workflow): Workflow object
        template_id (int): ID of the workflow template

    Returns:
        Workflow object
    """
    db_workflow = Workflow(
        display_name=workflow.display_name,
        description=workflow.description,
        spec_json=workflow.spec_json,
        uuid=uuid.uuid4(),
        files=[get_file_from_db(db, file_id) for file_id in workflow.file_ids],
        folder_id=workflow.folder_id,
        user_id=workflow.user_id,
    )

    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)
    return db_workflow


def update_workflow_in_db(db: Session, workflow: schemas.Workflow):
    """Update a workflow in the database.

    Args:
        db (Session): SQLAlchemy session object
        workflow (schemas.Workflow): Updated workflow schema

    Returns:
        Workflow object
    """
    workflow_in_db = get_workflow_from_db(db, workflow.id)
    for key, value in workflow.model_dump().items():
        setattr(workflow_in_db, key, value) if value else None
    db.commit()
    db.refresh(workflow_in_db)
    return workflow_in_db


def delete_workflow_from_db(db: Session, workflow_id: int):
    """Delete a workflow in the database.

    Args:
        db (Session): SQLAlchemy session object
        workflow_id (int): ID of the workflow
    """
    workflow = db.get(Workflow, workflow_id)
    db.delete(workflow)
    db.commit()


def delete_workflow_template_from_db(db: Session, workflow_template_id: int):
    """Deles a workflow template in the database.
    
    Args:
        db (Session): SQLAlchemy session object
        workflow_template_id (int): ID of the workflow template
    """
    workflow_template = db.get(WorkflowTemplate, workflow_template_id)
    if not workflow_template:
        raise ValueError(f"Workflow template with id {workflow_template_id} not found") 
    db.delete(workflow_template)
    db.commit()


def get_workflow_template_from_db(db: Session, template_id: int):
    """Get a workflow template by ID.

    Args:
        db (Session): SQLAlchemy session object
        template_id (int): ID of the workflow template

    Returns:
        Workflow template object
    """
    return db.get(WorkflowTemplate, template_id)


def get_workflow_templates_from_db(db: Session):
    """Get all workflow templates.

    Args:
        db (Session): SQLAlchemy session object

    Returns:
        List of WorkflowTemplate objects
    """
    return db.query(WorkflowTemplate).order_by(WorkflowTemplate.id.desc()).all()


def create_workflow_template_in_db(
    db: Session, template: schemas.WorkflowTemplateResponse
):
    """Create a new workflow template.

    Args:
        db (Session): SQLAlchemy session object
        template (WorkflowTemplate): Workflow template object

    Returns:
        WorkflowTemplate object
    """
    db_template = WorkflowTemplate(
        display_name=template.display_name,
        spec_json=template.spec_json,
        user_id=template.user_id,
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template


def get_task_from_db(db: Session, task_id: str):
    """Get a task by ID.

    Args:
        db (Session): SQLAlchemy session object
        task_id (str): ID of the task

    Returns:
        Task object
    """
    return db.get(Task, task_id)


def get_task_by_uuid_from_db(db: Session, uuid_string: str):
    """Get a task by Celery task ID.

    Args:
        db (Session): SQLAlchemy session object
        uuid_string (str): Celery task ID

    Returns:
        Task object
    """
    return db.query(Task).filter_by(uuid=uuid.UUID(uuid_string)).first()


def create_task_in_db(db: Session, task: schemas.Task):
    """Create a new task.

    Args:
        db (Session): SQLAlchemy session object
        task (Task): Task object

    Returns:
        Task object
    """
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
