import html
import json
import os
from typing import List
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, Form, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from auth.google import get_current_user

from datastores.sql.crud.file import (
    get_file_from_db,
    create_file_in_db,
    delete_file_from_db,
    get_file_summary_from_db,
    create_file_summary_in_db,
)
from datastores.sql.crud.folder import get_folder_from_db

from datastores.sql.crud.workflow import get_file_workflows_from_db, get_task_from_db
from datastores.sql.models.workflow import Task

from datastores.sql.database import get_db_connection
from lib.llm_summary import generate_summary
from lib.file_hashes import generate_hashes

from . import schemas

router = APIRouter()


# Get file
@router.get("/{file_id}")
def get_file(
    file_id: str, db: Session = Depends(get_db_connection)
) -> schemas.FileResponse:
    return get_file_from_db(db, int(file_id))


# Get file content
@router.get("/{file_id}/content", response_class=HTMLResponse)
def get_file_content(
    file_id: str, theme: str = "light", db: Session = Depends(get_db_connection)
):
    file = get_file_from_db(db, file_id)
    encodings_to_try = ["utf-8", "utf-16", "ISO-8859-1"]

    for encoding in encodings_to_try:
        try:
            with open(file.path, "r", encoding=encoding) as fh:
                content = fh.read()
                break
        except FileNotFoundError:
            content = "File not found"
        except UnicodeDecodeError:
            continue
    background_color = "#fff"
    font_color = "#000"
    if theme == "dark":
        background_color = "#000"
        font_color = "#fff"

    html_escaped_content = html.escape(content)
    html_content = f"""
    <html style="background:{background_color}">
        <pre style="color:{font_color};padding:10px;white-space: pre-wrap;">{ html_escaped_content }</pre>
    </html>
    """
    # return content
    return HTMLResponse(content=html_content, status_code=200)


# Download file
@router.post("/{file_id}/download")
def download_file(file_id: int, db: Session = Depends(get_db_connection)):
    file = get_file_from_db(db, file_id)
    headers = {"Access-Control-Expose-Headers": "Content-Disposition"}
    return FileResponse(
        path=file.path,
        filename=file.display_name,
        media_type="application/octet-stream",
        headers=headers,
    )


# Download file stream
@router.get("/{file_id}/download_stream")
async def download_file_stream(file_id: int, db: Session = Depends(get_db_connection)):
    file = get_file_from_db(db, file_id)
    file_path = file.path
    CHUNK_SIZE = 10 * 1024 * 1024  # 10MB

    async def iterfile():
        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(CHUNK_SIZE):
                print("chunk")
                yield chunk

    headers = {
        "Access-Control-Expose-Headers": "Content-Disposition",
        "Content-Disposition": f'attachment; filename="{file.display_name}"',
        "Content-Length": str(file.filesize),
    }

    print("return streaming response", headers)
    return StreamingResponse(
        iterfile(), headers=headers, media_type="application/octet-stream"
    )


# DISABLED: Delete file
# Deleting a file is complicated. E.g. This affects workflows that the file is part of.
# This needs a design and plan to handle such cases.
@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: int, db: Session = Depends(get_db_connection)):
    print("NOT IMPLEMENTED: Delete file")
    # delete_file_from_db(db, file_id)


# Create file
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_file(
    files: List[UploadFile],
    background_tasks: BackgroundTasks,
    folder_id: str = Form(),
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_user),
) -> List[schemas.FileResponse]:

    folder = get_folder_from_db(db, folder_id)
    files_in_db = []

    # Save file to disk
    for file in files:
        _, file_extension = os.path.splitext(file.filename)
        uuid = uuid4().hex
        output_filename = f"{uuid}{file_extension}"
        output_path = os.path.join(folder.path, output_filename)
        async with aiofiles.open(output_path, "wb") as fh:
            while content := await file.read(1024000):  # Read 1MB chunks
                await fh.write(content)

        # Save to database
        new_file_db = schemas.NewFileRequest(
            display_name=file.filename,
            uuid=uuid,
            filename=file.filename,
            extension=file_extension.lstrip("."),
            user_id=current_user.id,
        )
        if folder_id != "null":
            new_file_db.folder_id = int(folder_id)

        new_file = create_file_in_db(db, new_file_db.model_dump())
        files_in_db.append(new_file)

        background_tasks.add_task(generate_hashes, file_id=new_file.id)

    return files_in_db


# Get all workflows for a file
@router.get("/{file_id}/workflows")
def get_workflows(
    file_id: str, db: Session = Depends(get_db_connection)
) -> List[schemas.WorkflowResponse]:
    return get_file_workflows_from_db(db, file_id)


# Get task
@router.get("/{file_id}/workflows/{workflow_id}/tasks/{task_id}")
def get_task(
    file_id: int,
    workflow_id: int,
    task_id: int,
    db: Session = Depends(get_db_connection),
) -> List[schemas.Task]:
    return get_task_from_db(db, task_id)


# Download task result file
@router.post("/{file_id}/workflows/{workflow_id}/tasks/{task_id}/download")
def download_task_result(
    task_id: str,
    db: Session = Depends(get_db_connection),
):
    task = db.get(Task, task_id)
    result = json.loads(task.result)
    result_file_path = result.get("output_file_path")
    filename = os.path.basename(result_file_path)

    headers = {"Access-Control-Expose-Headers": "Content-Disposition"}
    return FileResponse(
        path=result_file_path,
        filename=filename,
        media_type="application/octet-stream",
        headers=headers,
    )


@router.get(
    "/{file_id}/summaries/{summary_id}", response_model=schemas.FileSummaryResponse
)
def get_file_summary(
    file_id: int,
    summary_id: int,
    db: Session = Depends(get_db_connection),
):
    return get_file_summary_from_db(db, summary_id)


@router.post("/{file_id}/summaries")
def generate_file_summary(
    file_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_connection),
):

    _file_summary = schemas.FileSummary(
        status_short="in_progress",
        file_id=file_id,
    )
    file_summary = create_file_summary_in_db(db, _file_summary.model_dump())
    background_tasks.add_task(
        generate_summary,
        llm_provider="ollama",
        llm_model="gemma2:9b",
        file_id=file_id,
        file_summary_id=file_summary.id,
    )
