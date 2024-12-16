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

import asyncio
from functools import wraps
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from datastores.sql.models.file import File
from datastores.sql.models.folder import Folder
from datastores.sql.models.role import Role
from datastores.sql.models.user import User, UserRole
from datastores.sql.models.group import GroupRole


class AuthorizationError(Exception):
    """Raised when a user does not have permission to access a resource."""

    def __init__(self, message: str):
        self.message = message


def raise_authorization_error(http_exception: bool, error_message: str):
    """Raises either HTTPException or AuthorizationError."""
    if http_exception:
        raise HTTPException(status_code=403, detail=error_message)
    else:
        raise AuthorizationError(error_message)


def check_user_access(
    db: Session,
    user: User,
    allowed_roles: list,
    folder: Folder = None,
    file: File = None,
):
    """
    Checks if a user has any of the allowed roles for a folder or file,
    considering both direct and inherited permissions (for files).
    Handles nested folders under revoked access folders.

    Args:
        db (Session): Database session.
        user (User): User object.
        allowed_roles (list): List of allowed roles.
        folder (Folder, optional): Folder object. Defaults to None.
        file (File, optional): File object. Defaults to None.

    Returns:
        bool: UserRole or GroupRole if authorized, False otherwise.

    Raises:
        ValueError: If neither folder nor file is provided.
    """
    if not db:
        raise ValueError("Database session (db) cannot be None.")
    if not user:
        raise ValueError("User object cannot be None.")
    if not folder and not file:
        raise ValueError("Either folder or file must be provided.")

    if file:
        file_role = (
            db.query(UserRole)
            .filter(UserRole.user_id == user.id, UserRole.file_id == file.id)
            .first()
        )
        if file_role and file_role.role in allowed_roles:
            return file_role

        # Check for file permissions via GroupRole
        for group in user.groups:
            group_role = (
                db.query(GroupRole)
                .filter(GroupRole.group_id == group.id, GroupRole.file_id == file.id)
                .first()
            )
            if group_role and group_role.role in allowed_roles:
                return group_role

        # If no explicit file permission, check folder permissions
        folder = file.folder

    while folder:
        folder_role = (
            db.query(UserRole)
            .filter(UserRole.user_id == user.id, UserRole.folder_id == folder.id)
            .first()
        )

        if folder_role:
            if folder_role.role == Role.NO_ACCESS:
                return False  # Explicitly denied access, stop traversal

            if folder_role.role in allowed_roles:
                return folder_role

        # Check for folder permissions via GroupRole
        for group in user.groups:
            group_role = (
                db.query(GroupRole)
                .filter(
                    GroupRole.group_id == group.id, GroupRole.folder_id == folder.id
                )
                .first()
            )
            if group_role and group_role.role in allowed_roles:
                return group_role

        folder = folder.parent

    return False  # No access found


def require_access(
    allowed_roles: list, http_exception: bool = True, error_message: str = None
):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            db = kwargs.get("db")
            folder_id = kwargs.get("folder_id")
            file_id = kwargs.get("file_id")
            current_user = kwargs.get("current_user")
            try:
                if folder_id:
                    folder = db.get(Folder, folder_id)
                    if not check_user_access(
                        db, current_user, allowed_roles, folder=folder
                    ):
                        raise_authorization_error(
                            http_exception, error_message or "No access to folder"
                        )

                if file_id:
                    file = db.get(File, file_id)
                    if not check_user_access(db, current_user, allowed_roles, file=file):
                        raise_authorization_error(
                            http_exception, error_message or "No access to file"
                        )
            except ValueError as exception:
                raise HTTPException(
                    status_code=404, detail="Folder or file not found.")
            # Await only if func is async
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)

            return func(*args, **kwargs)  # Call directly if func is sync

        return wrapper

    return decorator
