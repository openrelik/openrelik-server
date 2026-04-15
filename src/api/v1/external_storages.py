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

import logging
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from auth.common import get_current_active_user
from datastores.sql.crud.external_storage import (
    create_external_storage_in_db,
    delete_external_storage_from_db,
    get_external_storage_from_db,
    get_external_storages_from_db,
    register_external_file_in_db,
    update_external_storage_in_db,
)
from datastores.sql.database import get_db_connection

from . import schemas

router = APIRouter()


def _validate_no_traversal(relative_path: str) -> None:
    """Raise HTTP 400 if relative_path contains '..' components."""
    parts = relative_path.replace("\\", "/").split("/")
    if ".." in parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal detected in relative_path.",
        )


def _resolve_and_validate_path(mount_point: str, relative_path: str) -> str:
    """Resolve relative_path against mount_point and ensure it stays inside.

    Returns the resolved absolute path.

    Raises:
        HTTPException 400 if the resolved path escapes the mount point, does not
        exist, or is not a regular file.
    """
    joined = os.path.join(mount_point, relative_path.lstrip("/"))
    resolved = os.path.realpath(joined)
    mount_real = os.path.realpath(mount_point)

    # Ensure the resolved path stays inside the mount point.
    if resolved != mount_real and not resolved.startswith(mount_real + os.sep):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resolved path escapes the mount point.",
        )
    if not os.path.exists(resolved):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The specified path does not exist on disk.",
        )
    if not os.path.isfile(resolved):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The specified path is not a regular file.",
        )
    return resolved


# --- ExternalStorage CRUD ---

@router.get("/", response_model=List[schemas.ExternalStorageResponse])
def list_external_storages(
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """List all configured external storage locations."""
    return get_external_storages_from_db(db)


@router.post(
    "/",
    response_model=schemas.ExternalStorageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_external_storage(
    storage: schemas.ExternalStorageCreate,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Create a new external storage configuration."""
    if get_external_storage_from_db(db, storage.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"External storage '{storage.name}' already exists.",
        )
    return create_external_storage_in_db(db, storage)


@router.get("/{storage_name}", response_model=schemas.ExternalStorageResponse)
def get_external_storage(
    storage_name: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Get a single external storage by name."""
    storage = get_external_storage_from_db(db, storage_name)
    if not storage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"External storage '{storage_name}' not found.",
        )
    return storage


@router.patch("/{storage_name}", response_model=schemas.ExternalStorageResponse)
def update_external_storage(
    storage_name: str,
    update_data: schemas.ExternalStorageUpdate,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Update mount_point and/or description of an external storage."""
    storage = get_external_storage_from_db(db, storage_name)
    if not storage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"External storage '{storage_name}' not found.",
        )
    return update_external_storage_in_db(db, storage, update_data)


@router.delete("/{storage_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_external_storage(
    storage_name: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Delete an external storage and cascade all references.

    Any folders mounted to this storage are unmounted (external_storage_name set to
    null) and any lazily-registered File records that point to this storage are
    deleted from the database.  Physical files on disk are never touched.
    """
    storage = get_external_storage_from_db(db, storage_name)
    if not storage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"External storage '{storage_name}' not found.",
        )
    delete_external_storage_from_db(db, storage)


# --- Browse ---

@router.get("/{storage_name}/browse", response_model=schemas.BrowseResponse)
def browse_external_storage(
    storage_name: str,
    path: str = "",
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Browse a directory inside an external storage.

    Query parameter ``path`` is relative to the storage mount point.  When
    omitted the mount-point root is listed.
    """
    logger.debug("browse: storage_name=%r path=%r", storage_name, path)

    storage = get_external_storage_from_db(db, storage_name)
    if not storage:
        # get_external_storage_from_db logs a WARNING if the row exists but is
        # soft-deleted (is_deleted=True); here we just propagate the 404.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"External storage '{storage_name}' not found.",
        )

    logger.debug("browse: found storage id=%s mount_point=%r is_deleted=%s",
                 storage.id, storage.mount_point, storage.is_deleted)

    _validate_no_traversal(path)

    mount_real = os.path.realpath(storage.mount_point)
    joined = os.path.join(mount_real, path.lstrip("/"))
    resolved = os.path.realpath(joined)

    logger.debug("browse: mount_real=%r joined=%r resolved=%r", mount_real, joined, resolved)

    # Ensure resolved path stays inside the mount point.
    if resolved != mount_real and not resolved.startswith(mount_real + os.sep):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resolved path escapes the mount point.",
        )

    path_exists = os.path.exists(resolved)
    logger.debug("browse: os.path.exists(%r)=%s", resolved, path_exists)
    if not path_exists:
        logger.warning(
            "browse: resolved path %r does not exist (mount_point=%r, path=%r). "
            "Check that the filesystem is mounted and the server process has read access.",
            resolved, storage.mount_point, path,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The specified path does not exist.",
        )

    if not os.path.isdir(resolved):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The specified path is not a directory.",
        )

    items = []
    for entry in os.scandir(resolved):
        if entry.is_dir(follow_symlinks=False):
            items.append(schemas.BrowseItem(name=entry.name, type="directory", size=None))
        else:
            try:
                size = entry.stat(follow_symlinks=False).st_size
            except OSError:
                size = None
            items.append(schemas.BrowseItem(name=entry.name, type="file", size=size))

    # Directories first, then files; alphabetically within each group.
    items.sort(key=lambda i: (0 if i.type == "directory" else 1, i.name))

    return schemas.BrowseResponse(current_path=path, items=items)


# --- External file registration ---

@router.post(
    "/{storage_name}/files",
    response_model=schemas.FileResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_external_file(
    storage_name: str,
    request: schemas.ExternalFileRegisterRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Register an existing file from external storage into the VFS.

    Creates a File DB record pointing to the file without copying any data.
    The file is treated as read-only by all workers.
    """
    storage = get_external_storage_from_db(db, storage_name)
    if not storage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"External storage '{storage_name}' not found.",
        )

    _validate_no_traversal(request.relative_path)
    physical_path = _resolve_and_validate_path(storage.mount_point, request.relative_path)

    filename = os.path.basename(request.relative_path)
    display_name = request.display_name or filename

    extension = request.extension
    if not extension:
        _, ext = os.path.splitext(filename)
        extension = ext.lstrip(".") if ext else ""

    return register_external_file_in_db(
        db=db,
        storage=storage,
        relative_path=request.relative_path,
        physical_path=physical_path,
        folder_id=request.folder_id,
        display_name=display_name,
        extension=extension,
        current_user=current_user,
    )
