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
import glob
import html
import json
import os
from typing import List
from uuid import uuid4

import aiofiles
import redis
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from auth.common import get_current_active_user
from config import config, get_active_llms
from datastores.sql.crud.authz import require_access
from datastores.sql.crud.file import (
    create_file_in_db,
    create_file_summary_in_db,
    delete_file_from_db,
    get_file_from_db,
    get_file_summary_from_db,
)
from datastores.sql.crud.folder import get_folder_from_db
from datastores.sql.crud.workflow import get_file_workflows_from_db, get_task_from_db
from datastores.sql.database import get_db_connection
from datastores.sql.models.role import Role
from datastores.sql.models.workflow import Task
from lib.file_hashes import generate_hashes
from lib.llm_summary import generate_summary

from . import schemas

router = APIRouter()

# File types that are trusted to be returned unescaped to the client
ALLOWED_DATA_TYPES_PREVIEW = config.get("ui", {}).get("allowed_data_types_preview", [])

REDIS_URL = os.getenv("REDIS_URL")
redis_client = redis.Redis.from_url(REDIS_URL)


# Get file
# TODO: Return different response if folder is deleted.
@router.get("/{file_id}")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_file(
    file_id: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.FileResponse:
    """Get a file's metadata from the database."""
    return get_file_from_db(db, int(file_id))


# Get file content
@router.get("/{file_id}/content", response_class=HTMLResponse)
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_file_content(
    file_id: str,
    theme: str = "light",
    unescaped: bool = False,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> HTMLResponse:
    """Returns an HTML response with the file's content."""
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

    html_source_content = html.escape(content)
    if unescaped:
        if file.data_type in ALLOWED_DATA_TYPES_PREVIEW:
            html_source_content = content

    html_content = f"""
    <html style="background:{background_color}">
        <pre style="color:{font_color};padding:10px;white-space: pre-wrap;">{html_source_content}</pre>
    </html>
    """
    # return content
    return HTMLResponse(content=html_content, status_code=200)


# Download file
@router.get("/{file_id}/download")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def download_file(
    file_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> FileResponse:
    """Downloads a file's contents based on its ID."""
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
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
async def download_file_stream(
    file_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Downloads a file using streaming."""
    file = get_file_from_db(db, file_id)
    file_path = file.path
    CHUNK_SIZE = 10 * 1024 * 1024  # 10MB

    async def iterfile():
        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(CHUNK_SIZE):
                yield chunk

    headers = {
        "Access-Control-Expose-Headers": "Content-Disposition",
        "Content-Disposition": f'attachment; filename="{file.display_name}"',
        "Content-Length": str(file.filesize),
    }

    return StreamingResponse(iterfile(), headers=headers, media_type="application/octet-stream")


# Delete file
@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_access(allowed_roles=[Role.OWNER])
def delete_file(
    file_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    delete_file_from_db(db, file_id)


# Upload file
@router.post("/upload", status_code=status.HTTP_201_CREATED)
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def upload_files(
    file: UploadFile = File(...),
    resumableChunkNumber: int = Query(...),
    resumableChunkSize: int | None = None,
    resumableCurrentChunkSize: int | None = None,
    resumableTotalChunks: int = Query(...),
    resumableTotalSize: int | None = None,
    resumableIdentifier: str = Query(...),
    resumableFilename: str = Query(...),
    resumableRelativePath: str | None = None,
    folder_id: int = Query(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Uploads a file to the server.

    Returns:
        File: File metadata.
    """

    def _remove_chunks(chunks_to_remove: set) -> None:
        """Remove chunk files from disk.

        Args:
            chunks_to_remove (set): Set of chunk file paths to remove.
        """
        for chunk_path in chunks_to_remove:
            try:
                os.remove(chunk_path)
            except FileNotFoundError:
                pass

    MAX_CHUNK_RETRIES = 5

    # The folder that the file will be saved to.
    folder = get_folder_from_db(db, folder_id)

    # We need to keep state between requests to track the status of the uploaded chunks.
    # The resumableIdentifier is used to identify the upload session for a specific file.
    # The resumableChunkNumber is used to identify the chunk being uploaded.
    redis_uploaded_chunks_key = f"uploaded_chunks:{resumableIdentifier}"
    redis_upload_retries_key = f"upload_retries:{resumableIdentifier}:{resumableChunkNumber}"

    # Construct the chunk file path
    chunk_file_path = os.path.join(folder.path, f"{resumableIdentifier}.{resumableChunkNumber}")

    # If the chunk has been retried more than MAX_CHUNK_RETRIES times, remove all chunks and return
    # a 429 error to signal to the client to stop retrying uploading the chunk.
    retry_count = redis_client.get(redis_upload_retries_key)
    if retry_count and int(retry_count) >= MAX_CHUNK_RETRIES:
        chunk_pattern = os.path.join(folder.path, f"{resumableIdentifier}.*")
        chunks_to_remove = set(glob.glob(chunk_pattern))
        _remove_chunks(chunks_to_remove)
        redis_client.delete(redis_uploaded_chunks_key)
        redis_client.delete(redis_upload_retries_key)
        raise HTTPException(status_code=429, detail="Failed to upload file")

    # Save the chunk to disk. If the chunk fails to save return a 503 error to signal to the client
    # to retry the chunk.
    try:
        async with aiofiles.open(chunk_file_path, "wb") as fh:
            while content := await file.read(4096000):  # Read 4MB chunks
                await fh.write(content)
                redis_client.sadd(redis_uploaded_chunks_key, resumableChunkNumber)
    except Exception:
        redis_client.incr(redis_upload_retries_key, 1)
        raise HTTPException(status_code=503, detail="Failed to write chunk to disk")

    # Check if all chunks have been uploaded
    all_chunks_uploaded = (
        len(redis_client.smembers(redis_uploaded_chunks_key)) == resumableTotalChunks
    )

    # If not all chunks have been uploaded, return a 200 OK response to let the client know to
    # continue retrying uploading.
    if not all_chunks_uploaded:
        return

    # If all chunks have been successfully uploaded, remove the redis state keys.
    redis_client.delete(redis_uploaded_chunks_key)
    redis_client.delete(redis_upload_retries_key)

    # If all chunks has been uploaded then assemble the complete file.
    _, file_extension = os.path.splitext(resumableFilename)
    uuid = uuid4()
    output_filename = f"{uuid.hex}{file_extension}"
    output_path = os.path.join(folder.path, output_filename)

    chunks_to_remove = set()
    try:
        async with aiofiles.open(output_path, "wb") as outfile:
            for chunk_number in range(1, resumableTotalChunks + 1):
                chunk_path = os.path.join(folder.path, f"{resumableIdentifier}.{chunk_number}")
                async with aiofiles.open(chunk_path, "rb") as infile:
                    while content := await infile.read(1024000):  # Read 1MB chunks
                        await outfile.write(content)
                chunks_to_remove.add(chunk_path)
    except Exception:
        # If there is any error while writing the file, remove all chunks and return a 500 error.
        _remove_chunks(chunks_to_remove)
        raise HTTPException(status_code=500, detail="Failed to write file to disk")

    # Remove all temporary chunk files
    _remove_chunks(chunks_to_remove)

    # Save to database
    new_file = schemas.FileCreate(
        display_name=resumableFilename,
        uuid=uuid,
        filename=resumableFilename,
        extension=file_extension.lstrip("."),
        user_id=current_user.id,
    )

    if folder_id != "null":
        new_file.folder_id = int(folder_id)

    new_file_db = create_file_in_db(db, new_file, current_user)
    background_tasks.add_task(generate_hashes, file_id=new_file_db.id)

    return new_file_db


# Get all workflows for a file
@router.get(
    "/{file_id}/workflows",
    summary="Get all workflows for a file",
)
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_workflows(
    file_id: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.WorkflowResponse]:
    return get_file_workflows_from_db(db, file_id)


# Get task
@router.get("/{file_id}/workflows/{workflow_id}/tasks/{task_id}")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_task(
    file_id: int,
    workflow_id: int,
    task_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.TaskResponse]:
    return get_task_from_db(db, task_id)


# Download task result file
@router.post("/{file_id}/workflows/{workflow_id}/tasks/{task_id}/download")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def download_task_result(
    file_id: int,
    workflow_id: int,
    task_id: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> FileResponse:
    """Downloads a task result file based on its ID."""
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


@router.get("/{file_id}/summaries/{summary_id}", response_model=schemas.FileSummaryResponse)
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_file_summary(
    file_id: int,
    summary_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    return get_file_summary_from_db(db, summary_id)


@router.post("/{file_id}/summaries")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def generate_file_summary(
    file_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    new_file_summary = schemas.FileSummaryCreate(
        status_short="in_progress",
        file_id=file_id,
    )
    file_summary_db = create_file_summary_in_db(db, new_file_summary)
    active_llm = get_active_llms()[0]

    background_tasks.add_task(
        generate_summary,
        llm_provider=active_llm["name"],
        llm_model=active_llm["config"]["model"],
        file_id=file_id,
        file_summary_id=file_summary_db.id,
    )
