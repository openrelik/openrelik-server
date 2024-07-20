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

from datastores.sql.models.folder import Folder
from datastores.sql.models.user import User

from api.v1 import schemas


def get_folders_from_db(db: Session, folder_id: str):
    """Get all folders in a folder

    Args:
        db (Session): database session
        folder_id (str): folder id

    Returns:
        list: list of folders
    """
    return (
        db.query(Folder).filter_by(parent_id=folder_id).order_by(Folder.id.desc()).all()
    )


def get_folder_from_db(db: Session, folder_id: str):
    """Get a folder

    Args:
        db (Session): database session
        folder_id (int): folder id

    Returns:
        Folder: folder
    """
    return db.get(Folder, folder_id)


def create_folder_in_db(
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
        parent_id=new_folder.parent_id,
    )
    db.add(new_db_folder)
    db.commit()
    db.refresh(new_db_folder)

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
    folder_dict = folder.model_dump()
    folder_in_db = get_folder_from_db(db, folder.id)
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
