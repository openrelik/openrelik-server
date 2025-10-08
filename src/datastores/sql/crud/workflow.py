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
import uuid

from sqlalchemy.orm import Session

from api.v1 import schemas
from datastores.sql.crud.file import get_file_from_db
from datastores.sql.models.workflow import Task, TaskReport, Workflow, WorkflowTemplate
from lib import workflow_utils


def get_file_workflows_from_db(db: Session, file_id: int) -> list[Workflow]:
    """Get all workflows for a file.

    Args:
        db (Session): SQLAlchemy session object
        file_id (int): ID of the file

    Returns:
        List of Workflow objects
    """
    file = get_file_from_db(db, file_id)
    return file.workflows


def get_folder_workflows_from_db(db: Session, folder_id: int) -> list[Workflow]:
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


def get_workflow_from_db(db: Session, workflow_id: int) -> Workflow:
    """Get a workflow by ID.

    Args:
        db (Session): SQLAlchemy session object
        workflow_id (int): ID of the workflow

    Returns:
        Workflow object
    """
    return db.get(Workflow, workflow_id)


def create_workflow_in_db(db: Session, workflow: schemas.Workflow) -> Workflow:
    """Create a new workflow.

    Args:
        db (Session): SQLAlchemy session object
        workflow (Workflow): Workflow object

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
        template_id=workflow.template_id,
        user_id=workflow.user_id,
    )

    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)
    return db_workflow


def update_workflow_in_db(db: Session, workflow: schemas.Workflow) -> Workflow:
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


def get_workflow_template_from_db(db: Session, template_id: int) -> WorkflowTemplate:
    """Get a workflow template by ID.

    Args:
        db (Session): SQLAlchemy session object
        template_id (int): ID of the workflow template

    Returns:
        Workflow template object
    """
    return db.get(WorkflowTemplate, template_id)


def get_workflow_templates_from_db(db: Session) -> list[WorkflowTemplate]:
    """Get all workflow templates.

    Args:
        db (Session): SQLAlchemy session object

    Returns:
        List of WorkflowTemplate objects
    """

    def _get_and_update_templates():
        """
        Retrieve all workflow templates and update them to include unique param names if they
        don't already have them.

        Temporary function to ensure all templates have unique param names.
        Remove this function in the future once all templates have been updated.

        Returns:
            List of WorkflowTemplate objects
        """
        templates_to_return = []
        all_templates = db.query(WorkflowTemplate).order_by(WorkflowTemplate.id.desc()).all()

        for template in all_templates:
            # If the template does not have task_config, skip processing early
            if '"task_config"' not in template.spec_json:
                templates_to_return.append(template)
                continue

            # Check if the template already has param_name and skip if it does
            if '"param_name"' not in template.spec_json:
                try:
                    # Parse the JSON and add the param_name
                    spec_json_dict = json.loads(template.spec_json)
                    workflow_utils.add_unique_parameter_names(spec_json_dict)

                    # Update the database record
                    template.spec_json = json.dumps(spec_json_dict)
                    db.add(template)
                    db.commit()
                except (json.JSONDecodeError, KeyError):
                    pass

            templates_to_return.append(template)
        return templates_to_return

    # Temporary fix to update all templates to have unique param names. This ensures that
    # users can use the template parameters feature without manually updating the templates.
    # TODO: This should be removed in the future once all templates have been updated. Replace with
    # db.query(WorkflowTemplate).order_by(WorkflowTemplate.id.desc()).all()
    return _get_and_update_templates()


def create_workflow_template_in_db(
    db: Session, template: schemas.WorkflowTemplateResponse
) -> WorkflowTemplate:
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


def update_workflow_template_in_db(db: Session, template: WorkflowTemplate) -> WorkflowTemplate:
    """Update a workflow template.

    Args:
        db (Session): SQLAlchemy session object
        template (WorkflowTemplate): Workflow template object

    Returns:
        WorkflowTemplate object
    """
    template_in_db = db.get(WorkflowTemplate, template.id)
    for key, value in template.model_dump().items():
        setattr(template_in_db, key, value) if value else None
    db.commit()
    db.refresh(template_in_db)
    return template_in_db


def get_task_from_db(db: Session, task_id: str) -> Task:
    """Get a task by ID.

    Args:
        db (Session): SQLAlchemy session object
        task_id (str): ID of the task

    Returns:
        Task object
    """
    return db.get(Task, task_id)


def get_task_by_uuid_from_db(db: Session, uuid_string: str) -> Task:
    """Get a task by Celery task ID.

    Args:
        db (Session): SQLAlchemy session object
        uuid_string (str): Celery task ID

    Returns:
        Task object
    """
    return db.query(Task).filter_by(uuid=uuid.UUID(uuid_string)).first()


def create_task_in_db(db: Session, task: schemas.Task) -> Task:
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


def create_task_report_in_db(
    db: Session, task_report: schemas.TaskReportCreate, task_id: int
) -> TaskReport:
    """Creates a new file report in the database.

    Args:
        db (Session): A SQLAlchemy database session object.
        task_report (TaskReportCreate): The TaskReportCreate object.

    Returns:
        TaskReport: The newly created TaskReport object.
    """
    db_task_report = TaskReport(
        summary=task_report.summary,
        priority=task_report.priority,
        markdown=task_report.markdown,
        task_id=task_id,
    )
    db.add(db_task_report)
    db.commit()
    db.refresh(db_task_report)
    return db_task_report
