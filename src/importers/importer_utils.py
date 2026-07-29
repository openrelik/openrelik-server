# Copyright 2025 Google LLC
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
"""Shared helpers for cloud-object-store importers (GCS, S3)."""

import json
import os
import uuid
from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from api.v1 import schemas
from datastores.sql.crud.file import create_file_in_db
from datastores.sql.crud.folder import create_root_folder_in_db, create_subfolder_in_db
from datastores.sql.crud.user import get_user_from_db
from datastores.sql.models import file
from datastores.sql.models.folder import Folder
from datastores.sql.models.role import Role
from datastores.sql.models.user import UserRole


def parse_template_params(raw: str) -> Dict[str, Any]:
    """Parse workflow template parameters or return {} if unset."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Parameters are not valid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("Parameters must decode to a JSON object.")
    return parsed

def parse_positive_int_env(name: str, raw: str | None) -> int | None:
    """Parse ``raw`` as a positive integer, or return ``None`` if unset/blank.

    Intended for importer-module-level env-var parsing: failing at import
    time makes misconfiguration loud, rather than silently coercing at DB
    query time or crashing per-message.

    Args:
        name: The environment variable name (for error messages).
        raw: The raw env-var value (typically ``os.environ.get(name)``).

    Returns:
        The parsed positive integer, or ``None`` if ``raw`` is ``None`` or
        empty.

    Raises:
        ValueError: If ``raw`` is non-empty but not a positive integer.
    """
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except ValueError as e:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}") from e
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value}")
    return value


def extract_file_info(object_name: str) -> Tuple[int, str, str, str]:
    """Extract folder_id, filename, extension, and a UUID-based output filename.

    The object name / key is expected to be in the format
    ``folder_id/filename.extension``. The first path segment is parsed as the
    destination folder id; the remainder is kept as the filename (including
    any nested path).

    Args:
        object_name: The object name (GCS) or key (S3).

    Returns:
        A tuple of (folder_id, filename, file_extension, output_filename).

    Raises:
        ValueError: If the object name does not contain a forward slash, or
            if the folder-id segment is not a valid integer.
    """
    if "/" not in object_name:
        raise ValueError(
            f"Object name '{object_name}' does not contain a forward slash."
        )

    folder_id_str, filename = object_name.split("/", 1)
    folder_id = int(folder_id_str)
    _, file_extension = os.path.splitext(filename)
    file_uuid = uuid.uuid4()
    output_filename = f"{file_uuid.hex}{file_extension}"
    return folder_id, filename, file_extension, output_filename


def get_or_create_root_folder(db: Session, display_name: str, user_id: int) -> Folder:
    """Return the robot user's root folder with ``display_name``, creating it if missing.

    Matches on (display_name, parent_id IS NULL, owner=user_id) so importers
    that auto-ingest into per-case folders can idempotently land files in the
    right place across repeated events.

    Args:
        db: Database session.
        display_name: Folder name to look up or create.
        user_id: Owner id (typically the robot user).

    Returns:
        The existing or newly created root Folder.
    """
    owner = get_user_from_db(db, user_id)
    existing = (
        db.query(Folder)
        .join(UserRole, UserRole.folder_id == Folder.id)
        .filter(
            Folder.parent_id.is_(None),
            Folder.display_name == display_name,
            UserRole.user_id == owner.id,
            UserRole.role == Role.OWNER,
        )
        .first()
    )
    if existing:
        return existing

    return create_root_folder_in_db(
        db,
        schemas.FolderCreateRequest(display_name=display_name),
        owner,
    )


def get_or_create_subfolder(
    db: Session, parent_folder_id: int, display_name: str, user_id: int
) -> Folder:
    """Return the named subfolder under ``parent_folder_id``, creating it if missing.

    Matches on (display_name, parent_id=parent_folder_id, owner=user_id) so
    importers that mirror source layouts can idempotently land files under
    existing paths across repeated events.

    Args:
        db: Database session.
        parent_folder_id: The parent folder id to look under.
        display_name: Folder name to look up or create.
        user_id: Owner id (typically the robot user).

    Returns:
        The existing or newly created subfolder.
    """
    owner = get_user_from_db(db, user_id)
    existing = (
        db.query(Folder)
        .join(UserRole, UserRole.folder_id == Folder.id)
        .filter(
            Folder.parent_id == parent_folder_id,
            Folder.display_name == display_name,
            UserRole.user_id == owner.id,
            UserRole.role == Role.OWNER,
        )
        .first()
    )
    if existing:
        return existing

    return create_subfolder_in_db(
        db,
        parent_folder_id,
        schemas.FolderCreateRequest(display_name=display_name),
        owner,
    )


def create_file_record(
    db: object,
    filename: str,
    file_uuid: uuid.UUID,
    file_extension: str,
    folder_id: int,
    user_id: int,
) -> file.File:
    """Create a new file record in the database.

    Args:
        db: Database session.
        filename: The name of the file.
        file_uuid: The UUID of the file.
        file_extension: The file extension.
        folder_id: The ID of the folder the file belongs to.
        user_id: The ID of the user uploading the file.

    Returns:
        The newly created file record.
    """
    file_create_schema = schemas.FileCreate(
        display_name=filename,
        uuid=file_uuid,
        filename=filename,
        extension=file_extension.lstrip("."),
        folder_id=folder_id,
        user_id=user_id,
    )
    current_user = get_user_from_db(db, user_id)
    return create_file_in_db(db, file_create_schema, current_user)
