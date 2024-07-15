import os
from uuid import uuid4

from sqlalchemy.orm import Session

from datastores.sql.models.folder import Folder
from datastores.sql.models.user import User


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


def get_folder_from_db(db: Session, folder_id: int):
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
    folder: dict,
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
    new_folder = Folder(
        display_name=folder.get("display_name"),
        uuid=uuid4().hex,
        user=current_user,
        parent_id=folder.get("parent_id"),
    )
    db.add(new_folder)
    db.commit()
    db.refresh(new_folder)

    if not os.path.exists(new_folder.path):
        os.mkdir(new_folder.path)

    return new_folder


def update_folder_in_db(db: Session, folder: dict):
    """Update a folder in the database.

    Args:
        db (Session): SQLAlchemy session object
        folder (dict): Updated dictionary of a folder

    Returns:
        Folder object
    """
    folder_in_db = get_folder_from_db(db, folder.get("id"))
    for key, value in folder.items():
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
    db.delete(folder)
    db.commit()
