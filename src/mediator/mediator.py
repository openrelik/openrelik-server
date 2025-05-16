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

import base64
import json
import os
import time
import uuid

from celery import Celery
from celery.result import AsyncResult

from api.v1 import schemas

# Import models to make the ORM register correctly.
from datastores.sql import database
from datastores.sql.crud.file import create_file_in_db, create_file_report_in_db
from datastores.sql.crud.workflow import (
    create_task_report_in_db,
    get_task_by_uuid_from_db,
    get_workflow_from_db,
)
from lib.file_hashes import generate_hashes

# Number of times to retry database lookups
MAX_DATABASE_LOOKUP_RETRIES = 10
DATABASE_LOOKUP_RETRY_DELAY_SECONDS = 1


def get_task_from_db(db, task_uuid):
    """Retrieves a task from the database with retry logic.

    Args:
        db: The database session.
        task_uuid: The UUID of the task to retrieve.

    Returns:
        The task object if found, otherwise None.
    """
    task = None
    for retry_count in range(MAX_DATABASE_LOOKUP_RETRIES):
        task = get_task_by_uuid_from_db(db, task_uuid)
        if task:
            break
        print(f"Database lookup for task {task_uuid} failed, retrying..{retry_count + 1}")
        time.sleep(DATABASE_LOOKUP_RETRY_DELAY_SECONDS)
    return task


def update_database(db, model_instance):
    """Updates a model instance in the database.

    Args:
        db: The database session.
        model_instance: The model instance to update.
    """
    db.add(model_instance)
    db.commit()
    db.refresh(model_instance)


def create_file_in_database(db, file_data, task_result_dict, db_task):
    """Creates a file in the database based on the provided file data and task result.

    Args:
        db: The database session.
        file_data: A dictionary containing file data.
        task_result_dict: A dictionary containing task result data.
        db_task: The task object in the database.

    Returns:
        The created file object.
    """
    workflow = get_workflow_from_db(db, task_result_dict.get("workflow_id"))
    display_name = file_data.get("display_name")
    data_type = file_data.get("data_type")
    file_uuid = uuid.UUID(file_data.get("uuid"))
    file_extension = file_data.get("extension")
    original_path = file_data.get("original_path")
    source_file_id = file_data.get("source_file_id")
    new_file = schemas.FileCreate(
        display_name=display_name,
        uuid=file_uuid,
        filename=display_name,
        extension=file_extension.lstrip("."),
        original_path=original_path,
        data_type=data_type,
        folder_id=workflow.folder.id,
        user_id=workflow.user.id,
        source_file_id=source_file_id,
        task_output_id=db_task.id,
    )
    return create_file_in_db(db, new_file, workflow.user)


def process_task_progress_event(db, state, event):
    """Processes a task progress event and updates the database.

    Args:
        db: The database session.
        state: The Celery state object.
        event: The Celery event.
    """
    state.event(event)
    celery_task = state.tasks.get(event["uuid"])
    db_task = get_task_from_db(db, celery_task.uuid)
    db_task.status_short = celery_task.state
    db_task.status_progress = json.dumps(event.get("data"))
    update_database(db, db_task)


def process_successful_task(db, celery_task, db_task, celery_app):
    """Processes a successful Celery task and updates the database.

    Args:
        db: The database session.
        celery_task: The Celery task object.
        db_task: The task object in the database.
        celery_app: The Celery application.
    """
    celery_task_result = AsyncResult(celery_task.uuid, app=celery_app).get()
    result_dict = json.loads(base64.b64decode(celery_task_result.encode("utf-8")).decode("utf-8"))
    db_task.result = json.dumps(result_dict)

    output_files = result_dict.get("output_files", [])
    task_logs = result_dict.get("task_logs", [])
    file_reports = result_dict.get("file_reports", [])
    task_report = result_dict.get("task_report", {})

    # Create files from the resulting output files
    for file_data in output_files:
        new_file = create_file_in_database(db, file_data, result_dict, db_task)
        # TODO: Move this to a celery task to run in the background
        generate_hashes(new_file.id)

    # Create files from task log files
    for log_file_data in task_logs:
        new_log_file = create_file_in_database(db, log_file_data, result_dict, db_task)
        # TODO: Move this to a celery task to run in the background
        generate_hashes(new_log_file.id)

    for file_report in file_reports:
        new_file_report = schemas.FileReportCreate(
            summary=file_report.get("summary"),
            priority=file_report.get("priority"),
            input_file_uuid=file_report.get("input_file_uuid"),
            content_file_uuid=file_report.get("content_file_uuid"),
        )
        create_file_report_in_db(db, new_file_report, task_id=db_task.id)

    if task_report:
        new_task_report = schemas.TaskReportCreate(
            summary=task_report.get("summary"),
            priority=task_report.get("priority"),
            markdown=task_report.get("content"),
        )
        create_task_report_in_db(db, new_task_report, task_id=db_task.id)


def process_failed_task(db, celery_task, db_task):
    """Processes a failed Celery task and updates the database.

    Args:
        db: The database session.
        celery_task: The Celery task object.
        db_task: The task object in the database.
    """
    db_task.error_exception = celery_task.info().get("exception")
    db_task.error_traceback = celery_task.traceback


def process_task_event(db, state, event, celery_app):
    """Processes a task event and updates the database.

    Args:
        db: The database session.
        state: The Celery state object.
        event: The Celery event.
        celery_app: The Celery application.
    """
    state.event(event)
    celery_task = state.tasks.get(event["uuid"])
    db_task = get_task_from_db(db, celery_task.uuid)

    print(celery_task.uuid, event.get("type"), celery_task.state)

    if not db_task:
        # Task might not be in the database yet, skip processing
        return

    db_task.status_short = celery_task.state

    if celery_task.state == "SUCCESS":
        process_successful_task(db, celery_task, db_task, celery_app)
    elif celery_task.state == "FAILURE":
        process_failed_task(db, celery_task, db_task)

    db_task.runtime = celery_task.runtime
    update_database(db, db_task)


def monitor_celery_tasks(celery_app, db):
    """Monitor Celery tasks and update the database.

    Args:
        celery_app: The Celery application.
        db: The database session.
    """
    state = celery_app.events.State()

    def on_worker_event(event):
        if event.get("type") == "worker-heartbeat":
            return
        print("Event.type", event.get("type"))

    with celery_app.connection() as connection:
        recv = celery_app.events.Receiver(
            connection,
            handlers={
                "worker-heartbeat": on_worker_event,
                "worker-online": on_worker_event,
                "worker-offline": on_worker_event,
                "task-progress": lambda event: process_task_progress_event(db, state, event),
                "*": lambda event: process_task_event(db, state, event, celery_app),
            },
        )
        recv.capture(limit=None, timeout=None, wakeup=True)


if __name__ == "__main__":
    redis_url = os.getenv("REDIS_URL")
    celery_app = Celery(broker=redis_url, backend=redis_url)
    db = database.SessionLocal()
    # Start the Celery task monitoring loop
    monitor_celery_tasks(celery_app, db)
