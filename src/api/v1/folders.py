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

from typing import List, TYPE_CHECKING

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from auth.google import get_current_user
from datastores.sql.crud.file import get_files_from_db
from datastores.sql.crud.workflow import get_folder_workflows_from_db
from datastores.sql.crud.folder import (
    create_folder_in_db,
    update_folder_in_db,
    get_folder_from_db,
    get_folders_from_db,
    delete_folder_from_db,
)
from datastores.sql.database import get_db_connection

from . import schemas


router = APIRouter()


# Get all root folders
@router.get("/")
def get_root_folders(
    db: Session = Depends(get_db_connection),
) -> List[schemas.FolderResponse]:
    parent_folder = None
    return get_folders_from_db(db, parent_folder)


# Get folder
@router.get("/{folder_id}")
def get_folder(
    folder_id: str, db: Session = Depends(get_db_connection)
) -> schemas.FolderResponse:
    return get_folder_from_db(db, int(folder_id))


# Create folder
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_folder(
    request: schemas.FolderCreateRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_user),
) -> schemas.FolderResponse:
    folder_dict = request.model_dump()
    return create_folder_in_db(db, folder_dict, current_user)


# Update folder
@router.patch("/{folder_id}", response_model=schemas.FolderResponse)
async def update_folder(
    folder_id: int,
    folder_from_request: schemas.FolderCreateRequest,
    db: Session = Depends(get_db_connection),
):
    # Fetch folder to update from database
    folder_from_db = get_folder_from_db(db, folder_id)
    folder_model = schemas.FolderCreateRequest(**folder_from_db.__dict__)

    # Update workflow data with supplied values
    update_data = folder_from_request.model_dump(exclude_unset=True)
    updated_folder_model = folder_model.model_copy(update=update_data)

    return update_folder_in_db(db, updated_folder_model.model_dump())


# Get sub-folders for a folder
@router.get("/{folder_id}/folders/")
def get_folders(
    folder_id: str, db: Session = Depends(get_db_connection)
) -> List[schemas.FolderResponse]:
    return get_folders_from_db(db, folder_id)


# Get files for a folder
@router.get("/{folder_id}/files/")
def get_folder_files(
    folder_id: str, db: Session = Depends(get_db_connection)
) -> List[schemas.FileResponse]:
    return get_files_from_db(db, folder_id)


# Get workflows for a folder
@router.get("/{folder_id}/workflows")
def get_workflows(
    folder_id: str, db: Session = Depends(get_db_connection)
) -> List[schemas.WorkflowResponse]:
    return get_folder_workflows_from_db(db, folder_id)


# Delete folder
@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: int, db: Session = Depends(get_db_connection)):
    delete_folder_from_db(db, folder_id)
