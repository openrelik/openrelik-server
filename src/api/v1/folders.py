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
from typing import List

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from auth.common import get_current_active_user
from datastores.sql.crud.authz import check_user_access, require_access
from datastores.sql.crud.file import get_files_from_db
from datastores.sql.crud.folder import (
    create_root_folder_in_db,
    create_subfolder_in_db,
    delete_folder_from_db,
    get_folder_from_db,
    get_root_folders_from_db,
    get_shared_folders_from_db,
    get_subfolders_from_db,
    update_folder_in_db,
)
from datastores.sql.crud.group import create_group_role_in_db, delete_group_role_from_db
from datastores.sql.crud.user import create_user_role_in_db, delete_user_role_from_db
from datastores.sql.database import get_db_connection
from datastores.sql.models.role import Role

from . import schemas

router = APIRouter()


# Get all root folders for a user
@router.get("/")
def get_root_folders(
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.FolderResponseCompact]:
    """Get all root folders for a user.

    Args:
        db (Session): database session
        current_user (User): current user

    Returns:
        list: list of folders
    """
    return get_root_folders_from_db(db, current_user)


# Get all shared root folders for a user
@router.get("/shared/")
def get_shared_folders(
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.FolderResponseCompact]:
    """Get all shared folders for a user.

    Args:
        db (Session): database session
        current_user (User): current user

    Returns:
        list: list of folders
    """
    return get_shared_folders_from_db(db, current_user)


# Get all sub-folders for a parent folder
@router.get("/{folder_id}/folders/")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_subfolders(
    folder_id: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.FolderResponseCompact]:
    """
    Get all subfolders within a specified folder.

    Args:
        folder_id: The ID of the parent folder.
        db: The database session.
        current_user: The currently authenticated user.

    Returns:
        A list of subfolders within the specified folder.

    Raises:
        HTTPException: If the parent folder does not exist or the user does not have permission to access it.
    """
    return get_subfolders_from_db(db, parent_folder_id=folder_id)


# Get folder
@router.get("/{folder_id}")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_folder(
    folder_id: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.FolderResponse:
    """Get a folder from the database if the user has access.

    Args:
        folder_id: The ID of the folder to retrieve.
        db: The database session.
        current_user: The currently authenticated user.

    Returns:
        The folder object if found and the user has access.

    Raises:
        HTTPException: If the folder does not exist or the user does not have
        permission to access it.
    """
    if not folder_id:
        raise HTTPException(status_code=404, detail="Folder not found.")
    try:
        folder = get_folder_from_db(db, folder_id)
        if folder is None:
            raise HTTPException(status_code=404, detail="Folder not found.")
    except ValueError as exception:
        raise HTTPException(status_code=404, details=str(exception))
    if folder.is_deleted:
        raise HTTPException(status_code=404, detail="Folder is deleted.")
    return folder


# Create root folder
# No access check is necessary as active users can create their own root folders.
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_root_folder(
    new_folder_request: schemas.FolderCreateRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.FolderResponse:
    """Create a folder.

    Args:
        db (Session): database session
        new_folder_request (dict): dictionary for a folder
        current_user (User): current user

    Returns:
        Folder: folder

    Raises:
        HTTPException: If the user does not have permission to create a folder.
    """
    return create_root_folder_in_db(db, new_folder_request, current_user)


# Create subfolder
@router.post("/{folder_id}/folders/", status_code=status.HTTP_201_CREATED)
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
def create_subfolder(
    new_folder_request: schemas.FolderCreateRequest,
    folder_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.FolderResponse:
    """Create a sub folder.

    Args:
        db (Session): database session
        new_folder_request (dict): dictionary for a folder
        current_user (User): current user

    Returns:
        Folder: folder
    """
    return create_subfolder_in_db(db, folder_id, new_folder_request, current_user)


# Update folder
@router.patch("/{folder_id}")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def update_folder(
    folder_id: int,
    folder_from_request: schemas.FolderUpdateRequest,
    current_user: schemas.User = Depends(get_current_active_user),
    db: Session = Depends(get_db_connection),
) -> schemas.FolderResponse:
    """Update a folder in the database.

    Args:
        folder_id (int): The ID of the folder to update.
        folder_from_request (schemas.FolderUpdateRequest): The updated folder data.
        current_user (schemas.User): The currently authenticated user.
        db (Session): The database session.

    Returns:
        schemas.FolderResponse: The updated folder data.

    Raises:
        HTTPException: If the user does not have permission to update it.
    """
    folder_from_db = get_folder_from_db(db, folder_id)
    folder_model = schemas.FolderCreate(**folder_from_db.__dict__)

    # Update folder data with supplied values
    update_data = folder_from_request.model_dump(exclude_unset=True)
    updated_folder_model = folder_model.model_copy(update=update_data)

    return update_folder_in_db(db, updated_folder_model)


# Get files for a folder
@router.get("/{folder_id}/files/")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_folder_files(
    folder_id: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.FileResponseCompactList]:
    return get_files_from_db(db, folder_id)


# Delete folder
@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_access(allowed_roles=[Role.OWNER])
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    delete_folder_from_db(db, folder_id)


# Share folder
@router.post("/{folder_id}/roles")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
def share_folder(
    folder_id: int,
    request: schemas.FolderShareRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> None:
    """Share a folder.

    Args:
        db (Session): database session
        share_folder_request: dictionary for a share request
        current_user (User): current user

    Returns:
        Folder: folder
    """
    for user_id in request.user_ids:
        create_user_role_in_db(db, Role(request.user_role), user_id, folder_id)
    for group_id in request.group_ids:
        create_group_role_in_db(
            db, Role(request.group_role), group_id, folder_id)


@router.get("/{folder_id}/roles/me")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_my_folder_role(
    folder_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    try:
        folder = get_folder_from_db(db, folder_id)
    except ValueError as exception:
        raise HTTPException(status_code=404, details=str(exception))
    return check_user_access(
        db,
        current_user,
        allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER],
        folder=folder,
    )


@router.delete("/{folder_id}/roles/groups/{role_id}")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
def delete_group_role(
    folder_id: int,
    role_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    delete_group_role_from_db(db, role_id)


@router.delete("/{folder_id}/roles/users/{role_id}")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
def delete_user_role(
    folder_id: int,
    role_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    delete_user_role_from_db(db, role_id)
