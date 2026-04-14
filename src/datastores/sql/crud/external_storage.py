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
import uuid as uuid_module
from typing import List, Optional

import magic
from sqlalchemy.orm import Session

from api.v1 import schemas
from datastores.sql.models.external_storage import ExternalStorage

logger = logging.getLogger(__name__)
from datastores.sql.models.file import File
from datastores.sql.models.role import Role
from datastores.sql.models.user import UserRole


def get_external_storages_from_db(db: Session) -> List[ExternalStorage]:
    """Retrieve all configured external storages ordered by id."""
    return db.query(ExternalStorage).order_by(ExternalStorage.id.asc()).all()


def get_external_storage_from_db(db: Session, name: str) -> Optional[ExternalStorage]:
    """Retrieve a single ExternalStorage by its unique name."""
    # NOTE: the global before_compile listener in database.py automatically appends
    #   WHERE (is_deleted = FALSE OR is_deleted IS NULL)
    # to every query on entities that have is_deleted.  If the row exists but has
    # is_deleted = TRUE it will be silently filtered out and this function returns None.
    result = db.query(ExternalStorage).filter_by(name=name).first()
    if result is None:
        # Diagnostic: bypass the soft-delete filter to check whether the row exists at all.
        bypass_query = db.query(ExternalStorage).filter(ExternalStorage.name == name)
        bypass_query._include_deleted = True  # Tells before_compile to skip the filter.
        raw = bypass_query.first()
        if raw is not None:
            logger.warning(
                "get_external_storage_from_db: row name=%r exists in DB but is excluded "
                "by the soft-delete filter (is_deleted=%s). "
                "Fix: reset is_deleted=False on the record.",
                name,
                raw.is_deleted,
            )
        else:
            logger.debug("get_external_storage_from_db: no row at all found for name=%r", name)
    return result


def create_external_storage_in_db(
    db: Session, storage: schemas.ExternalStorageCreate
) -> ExternalStorage:
    """Create a new ExternalStorage record."""
    db_storage = ExternalStorage(**storage.model_dump())
    db.add(db_storage)
    db.commit()
    db.refresh(db_storage)
    return db_storage


def update_external_storage_in_db(
    db: Session,
    db_storage: ExternalStorage,
    update_data: schemas.ExternalStorageUpdate,
) -> ExternalStorage:
    """Update mount_point and/or description of an ExternalStorage."""
    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(db_storage, key, value)
    db.commit()
    db.refresh(db_storage)
    return db_storage


def delete_external_storage_from_db(db: Session, db_storage: ExternalStorage) -> bool:
    """Delete an ExternalStorage if no File records reference it.

    Returns:
        True if deleted, False if files still reference this storage.
    """
    file_count = (
        db.query(File).filter(File.external_storage_name == db_storage.name).count()
    )
    if file_count > 0:
        return False
    db.delete(db_storage)
    db.commit()
    return True


def register_external_file_in_db(
    db: Session,
    storage: ExternalStorage,
    relative_path: str,
    physical_path: str,
    folder_id: int,
    display_name: str,
    extension: str,
    current_user,
) -> File:
    """Create a File DB record that references an existing file in external storage.

    No data is copied. The record points to the file via external_storage_name and
    external_relative_path. The file is treated as read-only by workers.

    Args:
        db: SQLAlchemy session.
        storage: The ExternalStorage the file belongs to.
        relative_path: Path relative to storage.mount_point.
        physical_path: Resolved absolute path on disk (used for stat/magic).
        folder_id: VFS folder that should contain this file.
        display_name: Human-readable name for the file.
        extension: File extension (without leading dot).
        current_user: Authenticated user (ORM User model or object with .id).

    Returns:
        The newly created File ORM object.
    """
    filename = os.path.basename(relative_path)
    file_uuid = uuid_module.uuid4()

    db_file = File(
        display_name=display_name,
        uuid=file_uuid,
        filename=filename,
        filesize=os.path.getsize(physical_path),
        extension=extension,
        data_type="file:generic",
        magic_text=magic.from_file(physical_path),
        magic_mime=magic.from_file(physical_path, mime=True),
        folder_id=folder_id,
        user_id=current_user.id,
        external_storage_name=storage.name,
        external_relative_path=relative_path,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    user_role = UserRole(user=current_user, file=db_file, role=Role.OWNER)
    db.add(user_role)
    db.commit()

    return db_file
