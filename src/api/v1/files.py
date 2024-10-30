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
import html
import json
import os
from typing import List
from uuid import uuid4

import aiofiles
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    Query,
    File,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from auth.common import get_current_active_user
from config import config, get_active_cloud_provider
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
from datastores.sql.models.workflow import Task
from lib.constants import cloud_provider_data_type_mapping
from lib.file_hashes import generate_hashes
from lib.llm_summary import generate_summary

from . import schemas

router = APIRouter()

# File types that are trusted to be returned unescaped to the client
ALLOWED_DATA_TYPES_PREVIEW = config.get("ui", {}).get("allowed_data_types_preview", [])


# Get file
# TODO: Return different response if folder is deleted.
@router.get("/{file_id}")
def get_file(
    file_id: str, db: Session = Depends(get_db_connection)
) -> schemas.FileResponse:
    return get_file_from_db(db, int(file_id))


# Get file content
@router.get("/{file_id}/content", response_class=HTMLResponse)
def get_file_content(
    file_id: str,
    theme: str = "light",
    unescaped: bool = False,
    db: Session = Depends(get_db_connection),
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

    html_source_content = html.escape(content)
    if unescaped:
        if file.data_type in ALLOWED_DATA_TYPES_PREVIEW:
            html_source_content = content

    html_content = f"""
    <html style="background:{background_color}">
        <pre style="color:{font_color};padding:10px;white-space: pre-wrap;">{ html_source_content }</pre>
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
                yield chunk

    headers = {
        "Access-Control-Expose-Headers": "Content-Disposition",
        "Content-Disposition": f'attachment; filename="{file.display_name}"',
        "Content-Length": str(file.filesize),
    }

    return StreamingResponse(
        iterfile(), headers=headers, media_type="application/octet-stream"
    )


# Delete file
@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: int, db: Session = Depends(get_db_connection)):
    delete_file_from_db(db, file_id)


# Upload file
@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_files(
    file: UploadFile = File(...),
    resumableChunkNumber: int = Query(...),
    resumableChunkSize: int = Query(...),
    resumableCurrentChunkSize: int = Query(...),
    resumableTotalChunks: int = Query(...),
    resumableTotalSize: int = Query(...),
    resumableIdentifier: str = Query(...),
    resumableFilename: str = Query(...),
    resumableRelativePath: str = Query(...),
    folder_id: int = Query(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    is_last_chunk = resumableChunkNumber == resumableTotalChunks
    folder = get_folder_from_db(db, folder_id)

    # Construct the chunk file path
    chunk_file_path = os.path.join(
        folder.path, f"{resumableIdentifier}.{resumableChunkNumber}"
    )

    # Save the chunk to disk
    async with aiofiles.open(chunk_file_path, "wb") as fh:
        while content := await file.read(1024000):  # Read 1MB chunks
            await fh.write(content)

    # Return early if this is NOT the last chunk.
    if not is_last_chunk:
        return

    # If all chunks has been uploaded then assemble the complete file.
    _, file_extension = os.path.splitext(resumableFilename)
    uuid = uuid4()
    output_filename = f"{uuid.hex}{file_extension}"
    output_path = os.path.join(folder.path, output_filename)

    async with aiofiles.open(output_path, "wb") as outfile:
        for chunk_number in range(1, resumableTotalChunks + 1):
            chunk_path = os.path.join(
                folder.path, f"{resumableIdentifier}.{chunk_number}"
            )
            async with aiofiles.open(chunk_path, "rb") as infile:
                while content := await infile.read(1024000):  # Read 1MB chunks
                    await outfile.write(content)
            # Remove the temporary chunk file.
            os.remove(chunk_path)

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

    new_file_db = create_file_in_db(db, new_file)
    background_tasks.add_task(generate_hashes, file_id=new_file_db.id)

    return new_file_db


# Create cloud disk file
@router.post("/cloud", status_code=status.HTTP_201_CREATED)
async def create_cloud_disk_file(
    background_tasks: BackgroundTasks,
    request: schemas.CloudDiskCreateRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.FileResponse:

    folder = get_folder_from_db(db, request.folder_id)

    # Save file to disk
    uuid = uuid4()
    output_filename = f"{uuid.hex}.json"
    output_path = os.path.join(folder.path, output_filename)

    cloud_provider = get_active_cloud_provider()
    cloud_provider["disk_name"] = request.disk_name

    with open(output_path, "w") as fh:
        fh.write(json.dumps(cloud_provider))

    # Save to database
    new_file = schemas.FileCreate(
        display_name=request.disk_name,
        uuid=uuid,
        data_type=cloud_provider_data_type_mapping.get(cloud_provider["name"]),
        filename=request.disk_name,
        extension="json",
        user_id=current_user.id,
    )
    if request.folder_id != "null":
        new_file.folder_id = int(request.folder_id)

    new_file_db = create_file_in_db(db, new_file)
    background_tasks.add_task(generate_hashes, file_id=new_file_db.id)

    return new_file_db


# Get all workflows for a file
@router.get(
    "/{file_id}/workflows",
    summary="Get all workflows for a file",
)
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
    file_id: int,
    workflow_id: int,
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

    new_file_summary = schemas.FileSummaryCreate(
        status_short="in_progress",
        file_id=file_id,
    )
    file_summary_db = create_file_summary_in_db(db, new_file_summary)
    background_tasks.add_task(
        generate_summary,
        llm_provider="ollama",
        llm_model="gemma2:9b",
        file_id=file_id,
        file_summary_id=file_summary_db.id,
    )
