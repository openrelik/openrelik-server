import base64
import json
import os
import time

from celery import Celery
from celery.result import AsyncResult

# Import models to make the ORM register correctly.
from datastores.sql import database
from datastores.sql.models import file, folder, user, workflow

from datastores.sql.crud.file import create_file_in_db
from datastores.sql.crud.workflow import get_task_by_uuid_from_db, get_workflow_from_db

from api.v1 import schemas

from lib.file_hashes import generate_hashes


def get_task_from_db(db, task_uuid):
    """Get a task from the database."""
    task = get_task_by_uuid_from_db(db, task_uuid)
    max_retries = 10
    retry_count = 0
    sleep_s = 1
    while not task and retry_count < max_retries:
        time.sleep(sleep_s)
        task = get_task_by_uuid_from_db(db, task_uuid)
        retry_count += 1
        print(f"{task_uuid} Database lookup failed, retrying..{retry_count}")
    return task


def my_monitor(app, db):
    """Monitor Celery tasks."""
    state = app.events.State()

    def update_database(model_instance):
        db.add(model_instance)
        db.commit()
        db.refresh(model_instance)

    def on_worker_event(event):
        if event.get("type") == "worker-heartbeat":
            return
        print("Event.type", event.get("type"))

    def on_task_progress_event(event):
        state.event(event)
        celery_task = state.tasks.get(event["uuid"])
        db_task = get_task_from_db(db, celery_task.uuid)
        db_task.status_short = celery_task.state
        db_task.status_progress = json.dumps(event.get("data"))
        update_database(db_task)

    def on_task_event(event):
        state.event(event)
        celery_task = state.tasks.get(event["uuid"])
        print(celery_task.uuid, event.get("type"), celery_task.state)
        celery_task_info = celery_task.info()
        db_task = get_task_from_db(db, celery_task.uuid)
        db_task.status_short = celery_task.state
        if celery_task.state == "SUCCESS":
            # Result is base64 encoded from the task because Celery stringify the dict
            # and the means we cannot serialize it to valid json.
            celery_task_result = AsyncResult(celery_task.uuid, app=app).get()
            result_string = base64.b64decode(celery_task_result.encode("utf-8")).decode(
                "utf-8"
            )
            result_dict = json.loads(result_string)
            result_json = json.dumps(result_dict)

            # Update task result
            db_task.result = result_json

            # Create files from the resulting output files
            for file in result_dict.get("output_files"):
                workflow = get_workflow_from_db(db, result_dict.get("workflow_id"))
                filename = file.get("filename")
                _, file_extension = os.path.splitext(filename)
                new_file_db = schemas.NewFileRequest(
                    display_name=filename,
                    uuid=file.get("uuid"),
                    filename=filename,
                    extension=file_extension.lstrip("."),
                    folder_id=workflow.folder.id,
                    user_id=workflow.user.id,
                    task_output_id=db_task.id,
                )
                print(new_file_db.model_dump())
                new_file = create_file_in_db(db, new_file_db.model_dump())
                # TODO: Move this to a celery task to run in the background
                generate_hashes(new_file.id)

        if celery_task.state == "FAILURE":
            db_task.error_exception = celery_task_info.get("exception")
            db_task.error_traceback = celery_task.traceback
        db_task.runtime = celery_task.runtime
        update_database(db_task)

    with app.connection() as connection:
        recv = app.events.Receiver(
            connection,
            handlers={
                "worker-heartbeat": on_worker_event,
                "worker-online": on_worker_event,
                "worker-offline": on_worker_event,
                "task-progress": on_task_progress_event,
                "*": on_task_event,
            },
        )
        recv.capture(limit=None, timeout=None, wakeup=True)


if __name__ == "__main__":
    redis_url = os.getenv("REDIS_URL")
    app = Celery(broker=redis_url, backend=redis_url)
    db = database.SessionLocal()
    my_monitor(app, db)
