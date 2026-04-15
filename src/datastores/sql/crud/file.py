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
import uuid

import magic
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from api.v1 import schemas
from datastores.sql.models.file import File, FileChat, FileChatMessage, FileReport, FileSummary
from datastores.sql.models.role import Role
from datastores.sql.models.user import User, UserRole

from .folder import get_folder_from_db


def get_files_from_db(db: Session, folder_id: int):
    """Retrieves a list of files from the database for a specific folder.

    Args:
        db (Session): A SQLAlchemy database session object.
        folder_id (str): The ID of the folder to retrieve files from.

    Returns:
        List[File]: A list of File objects representing the files in the folder.
    """
    return db.query(File).filter_by(folder_id=folder_id).order_by(File.id.desc()).all()


def sync_external_mount_files_in_db(db: Session, folder, current_user) -> None:
    """Lazily register files from a folder's external mount into the DB.

    Recursively walks the directory at
    (ExternalStorage.mount_point / folder.external_base_path) and creates File
    DB records for any regular files not already registered. Idempotent.
    Symbolic links are skipped. Symbolic-link directories are not followed.

    Args:
        db: SQLAlchemy session.
        folder: Folder ORM object with external_storage_name set.
        current_user: Authenticated user assigned as owner of newly created records.

    Raises:
        ValueError: If the storage is not found, the path escapes the mount point,
                    or the resolved path is not a directory.
    """
    from datastores.sql.crud.external_storage import (
        get_external_storage_from_db,
        register_external_file_in_db,
    )

    storage = get_external_storage_from_db(db, folder.external_storage_name)
    if not storage:
        raise ValueError(f"External storage '{folder.external_storage_name}' not found.")

    base = folder.external_base_path or ""
    resolved_dir = os.path.realpath(os.path.join(storage.mount_point, base.lstrip("/")))
    mount_real = os.path.realpath(storage.mount_point)

    if resolved_dir != mount_real and not resolved_dir.startswith(mount_real + os.sep):
        raise ValueError(
            f"external_base_path '{base}' escapes mount point '{storage.mount_point}'."
        )
    if not os.path.isdir(resolved_dir):
        raise ValueError(f"External base path '{resolved_dir}' is not a directory.")

    # Pre-load existing registered paths in a single query to avoid N+1 on large trees.
    existing_paths = {
        row.external_relative_path
        for row in db.query(File.external_relative_path)
        .filter_by(folder_id=folder.id, external_storage_name=folder.external_storage_name)
        .all()
    }

    for dirpath, _dirnames, filenames in os.walk(resolved_dir, followlinks=False):
        for filename in filenames:
            physical_path = os.path.join(dirpath, filename)

            # Skip symbolic links — consistent with the original scandir behaviour.
            if os.path.islink(physical_path):
                continue

            # relative_path is always relative to mount_point, so nested files
            # naturally include their subdirectory prefix (e.g. "evidence/file.bin").
            relative_path = os.path.relpath(physical_path, storage.mount_point)
            if relative_path in existing_paths:
                continue

            display_name = filename
            _, ext = os.path.splitext(filename)
            extension = ext.lstrip(".") if ext else ""
            try:
                register_external_file_in_db(
                    db,
                    storage,
                    relative_path,
                    physical_path,
                    folder.id,
                    display_name,
                    extension,
                    current_user,
                )
            except IntegrityError:
                # Another concurrent request registered the same file — safe to ignore.
                db.rollback()
                logger.debug(
                    "sync_external_mount: IntegrityError for '%s' in folder %s "
                    "(concurrent insert)",
                    relative_path,
                    folder.id,
                )


def get_file_from_db(db: Session, file_id: int):
    """Retrieves a file from the database by its ID.

    Args:
        db (Session): A SQLAlchemy database session object.
        file_id (int): The ID of the file to retrieve.

    Returns:
        File: A File object representing the file with the specified ID.
    """
    return db.get(File, file_id)


def get_file_by_uuid_from_db(db: Session, uuid_string: str):
    """Get a file by uuid.

    Args:
        db (Session): SQLAlchemy session object
        uuid (uuid.UUID): File uuid

    Returns:
        File object
    """
    return db.query(File).filter_by(uuid=uuid.UUID(uuid_string)).first()


def create_file_in_db(db: Session, file: schemas.FileCreate, current_user: User):
    """Creates a new file in the database.

    Args:
        db (Session): A SQLAlchemy database session object.
        file (dict): A dictionary representing the file to be created.

    Returns:
        File: The newly created File object.
    """
    folder = get_folder_from_db(db, file.folder_id)
    uuid = file.uuid
    output_filename = uuid.hex
    if file.extension:
        output_filename = f"{uuid.hex}.{file.extension}"
    output_file = os.path.join(folder.path, output_filename)

    # File metadata
    file.magic_text = magic.from_file(output_file)
    file.magic_mime = magic.from_file(output_file, mime=True)
    file.filesize = os.stat(output_file).st_size

    if not file.data_type:
        file.data_type = "file:generic"

    db_file = File(**file.model_dump())
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    user_role = UserRole(user=current_user, file=db_file, role=Role.OWNER)
    db.add(user_role)
    db.commit()

    return db_file


def delete_file_from_db(db: Session, file_id: int):
    """Delete a file from the database by its ID.

    Args:
        db (Session): A SQLAlchemy database session object.
        file_id (int): The ID of the file representing the file to be deleted.
    """
    file = db.get(File, file_id)
    file.soft_delete()
    db.commit()


def get_file_summary_from_db(db: Session, file_summary_id: int):
    """Retrieves a file summary from the database by its ID."""
    return db.get(FileSummary, file_summary_id)


def create_file_summary_in_db(db: Session, file_summary: schemas.FileSummaryCreate):
    """Creates a new file summary in the database using generative AI.

    Args:
        db (Session): A SQLAlchemy database session object.
        file_summary (dict): A dictionary representing a FileSummary.

    Returns:
        FileSummary: The newly created FileSummary object.
    """
    db_file_summary = FileSummary(**file_summary.model_dump())
    db.add(db_file_summary)
    db.commit()
    db.refresh(db_file_summary)
    return db_file_summary


def update_file_summary_in_db(db: Session, file_summary: FileSummary):
    """Update a FileSummary object in the database.

    Args:
        db (Session): SQLAlchemy session object
        file_summary (FileSummary): FileSummary object to be updated

    Returns:
        FileSummary: Updated FileSummary object
    """
    db.add(file_summary)
    db.commit()
    db.refresh(file_summary)
    return file_summary


def create_file_report_in_db(db: Session, file_report: schemas.FileReportCreate, task_id: int):
    """Creates a new file report in the database.

    Args:
        db (Session): A SQLAlchemy database session object.
        file_report (dict): A dictionary representing a FileReport.

    Returns:
        FileReport: The newly created FileReport object.
    """
    input_file = get_file_by_uuid_from_db(db, file_report.input_file_uuid)
    content_file = get_file_by_uuid_from_db(db, file_report.content_file_uuid)

    with open(content_file.path, "r") as fh:
        content = fh.read()

    db_file_report = FileReport(
        summary=file_report.summary,
        priority=file_report.priority,
        markdown=content,
        file=input_file,
        content_file=content_file,
        task_id=task_id,
    )
    db.add(db_file_report)
    db.commit()
    db.refresh(db_file_report)
    return db_file_report


def create_file_chat_in_db(db: Session, file_chat: schemas.FileChatCreate):
    """Creates a new file chat in the database.

    Args:
        db (Session): A SQLAlchemy database session object.
        file_chat (dict): A dictionary representing a FileChat.

    Returns:
        FileChat: The newly created FileChat object.
    """
    db_file_chat = FileChat(**file_chat.model_dump())
    db.add(db_file_chat)
    db.commit()
    db.refresh(db_file_chat)

    return db_file_chat


def create_file_chat_message_in_db(db: Session, file_chat_message: schemas.FileChatMessageCreate):
    """Creates a new file chat message in the database.

    Args:
        db (Session): A SQLAlchemy database session object.
        file_chat_message (dict): A dictionary representing a FileChatMessage.

    Returns:
        FileChatMessage: The newly created FileChatMessage object.
    """
    db_file_chat_message = FileChatMessage(**file_chat_message.model_dump())
    db.add(db_file_chat_message)
    db.commit()
    db.refresh(db_file_chat_message)

    return db_file_chat_message


def get_latest_file_chat_from_db(db: Session, file_id: int, user_id: int):
    """Retrieves the latest file chat from the database for a specific file.

    Args:
        db (Session): A SQLAlchemy database session object.
        file_id (int): The ID of the file to retrieve the latest chat from.

    Returns:
        FileChat: The latest FileChat object for the specified file.
    """
    return (
        db.query(FileChat)
        .filter_by(file_id=file_id, user_id=user_id)
        .order_by(FileChat.id.desc())
        .first()
    )
