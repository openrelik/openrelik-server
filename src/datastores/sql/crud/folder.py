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

import os
import uuid

from sqlalchemy.orm import Session
from sqlalchemy.sql import and_

from api.v1 import schemas
from datastores.sql.models.folder import Folder
from datastores.sql.models.group import Group, GroupRole
from datastores.sql.models.role import Role
from datastores.sql.models.user import User, UserRole


def get_root_folders_from_db(db: Session, current_user: User):
    """Get all root folders for a user.

    Args:
        db (Session): database session
        current_user (User): current user

    Returns:
        list: list of folders
    """
    return (
        db.query(Folder)
        .join(UserRole, UserRole.folder_id == Folder.id)
        .filter(
            UserRole.user_id == current_user.id,
            UserRole.role == Role.OWNER,
            Folder.parent_id.is_(None),
        )
        .all()
    )


def get_shared_folders_from_db(db: Session, current_user: User):
    """Get all shared folders for a user.

    Args:
        db (Session): database session
        current_user (User): current user

    Returns:
        list: list of folders
    """
    # Get folders shared directly with the user
    user_folders = (
        db.query(Folder.id.label("id"))
        .join(UserRole, UserRole.folder_id == Folder.id)
        .filter(
            UserRole.user_id == current_user.id,
            UserRole.role != Role.OWNER,
        )
    )

    # Get folders shared with groups the user is a member of
    group_folders = (
        db.query(Folder.id.label("id"))
        .join(GroupRole, GroupRole.folder_id == Folder.id)
        .join(Group, Group.id == GroupRole.group_id)
        .filter(Group.users.any(id=current_user.id))
    )

    # Combine the results and exclude folders where the user is the owner
    shared_folders = user_folders.union(group_folders).subquery()

    return (
        db.query(Folder)
        .select_from(shared_folders)  # Use select_from to make the join explicit
        .join(
            Folder, Folder.id == shared_folders.c.id
        )  # Specify the join condition here
        .outerjoin(
            UserRole,
            and_(
                UserRole.folder_id == Folder.id,
                UserRole.user_id == current_user.id,
                UserRole.role == Role.OWNER,
            ),
        )
        .filter(UserRole.id.is_(None))
        .all()
    )


def get_subfolders_from_db(db: Session, parent_folder_id: str):
    """Get all folders in a folder

    Args:
        db (Session): database session
        folder_id (str): folder id

    Returns:
        list: list of folders
    """
    return (
        db.query(Folder)
        .filter_by(parent_id=parent_folder_id)
        .order_by(Folder.id.desc())
        .all()
    )


def get_folder_from_db(db: Session, folder_id: int):
    """Get a folder from the database by its ID.

    Args:
        db (Session): database session
        folder_id (int): folder id

    Returns:
        Folder object
    """
    return db.get(Folder, folder_id)


def create_root_folder_in_db(
    db: Session,
    new_folder: schemas.FolderCreateRequest,
    current_user: User,
):
    """Create a folder

    Args:
        db (Session): database session
        folder (dict): dictionary for a folder
        current_user (User): current user

    Returns:
        Folder: folder
    """
    new_db_folder = Folder(
        display_name=new_folder.display_name,
        uuid=uuid.uuid4(),
        user=current_user,
        parent_id=None,
    )
    db.add(new_db_folder)
    db.commit()
    db.refresh(new_db_folder)

    user_role = UserRole(user=current_user, folder=new_db_folder, role=Role.OWNER)
    db.add(user_role)
    db.commit()

    if not os.path.exists(new_db_folder.path):
        os.mkdir(new_db_folder.path)

    return new_db_folder


def create_subfolder_in_db(
    db: Session,
    folder_id: int,
    new_folder: schemas.FolderCreateRequest,
    current_user: User,
):
    """Create a folder

    Args:
        db (Session): database session
        folder_id (int): parent folder id
        new_folder (dict): dictionary for a folder
        current_user (User): current user

    Returns:
        Folder: folder
    """
    new_db_folder = Folder(
        display_name=new_folder.display_name,
        uuid=uuid.uuid4(),
        user=current_user,
        parent_id=folder_id,
    )
    db.add(new_db_folder)
    db.commit()
    db.refresh(new_db_folder)

    user_role = UserRole(user=current_user, folder=new_db_folder, role=Role.OWNER)
    db.add(user_role)
    db.commit()

    if not os.path.exists(new_db_folder.path):
        os.mkdir(new_db_folder.path)

    return new_db_folder


def update_folder_in_db(db: Session, folder: schemas.FolderUpdateRequest):
    """Update a folder in the database.

    Args:
        db (Session): SQLAlchemy session object
        folder (dict): Updated dictionary of a folder

    Returns:
        Folder object
    """
    folder_in_db = db.get(Folder, folder.id)
    folder_dict = folder.model_dump()
    for key, value in folder_dict.items():
        setattr(folder_in_db, key, value) if value else None
    db.commit()
    db.refresh(folder_in_db)
    return folder_in_db


def delete_folder_from_db(db: Session, folder_id: int):
    """Delete a folder from the database by its ID.

    Args:
        db (Session): A SQLAlchemy database session object.
        folder_id (int): The ID of the folder to be deleted.
    """
    folder = db.get(Folder, folder_id)

    def _recursive_soft_delete(folder: Folder):
        """Recursive function to delete all files and subfolders."""
        for file in folder.files:
            file.soft_delete(db)

        for child_folder in folder.children:
            _recursive_soft_delete(child_folder)

        folder.soft_delete(db)

    _recursive_soft_delete(folder)
    db.commit()
