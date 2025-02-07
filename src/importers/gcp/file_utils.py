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
import logging
import uuid
import os

from typing import Tuple

from api.v1 import schemas
from datastores.sql.crud.file import create_file_in_db
from datastores.sql.crud.user import get_user_from_db
from datastores.sql.models import file

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_file_info(object_name: str) -> Tuple[int, str, str, str]:
    """
    Extracts folder_id, filename, extension, and a UUID from the object name.

    The object name is expected to be in the format: "folder_id/filename.extension".

    Args:
        object_name (str): The name of the object in GCS, which includes folder_id and filename.

    Returns:
        Tuple[int, str, str, str]: A tuple containing folder_id (int), filename (str),
        file_extension (str), and output_filename (str).

    Raises:
        ValueError: If the object_name does not contain a forward slash.
        Exception: If there is an error extracting the file information.
    """
    try:
        if "/" not in object_name:
            raise ValueError(f"Object name '{object_name}' does not contain a forward slash.")

        folder_id_str, filename = object_name.split("/", 1)
        folder_id = int(folder_id_str)
        _, file_extension = os.path.splitext(filename)
        file_uuid = uuid.uuid4()
        output_filename = f"{file_uuid.hex}{file_extension}"
        return folder_id, filename, file_extension, output_filename
    except ValueError as ve:
        logger.error(f"Invalid object name format: {ve}")
        raise
    except Exception as e:
        logger.exception(f"Error extracting file info: {e}")
        raise

def create_file_record(
    db: object,
    filename: str,
    file_uuid: uuid.UUID,
    file_extension: str,
    folder_id: int,
    user_id: int,
) -> file.File:
    """
    Creates a new file record in the database.

    Args:
        db: Database session.
        filename (str): The name of the file.
        file_uuid (uuid.UUID): The UUID of the file.
        file_extension (str): The file extension.
        folder_id (int): The ID of the folder the file belongs to.
        user_id (int): The ID of the user uploading the file.

    Returns:
        file.File: The newly created file record.

    Raises:
        Exception: If there is an error creating the file record.
    """
    try:
        # Create a FileCreate schema object
        file_create_schema = schemas.FileCreate(
            display_name=filename,
            uuid=file_uuid,
            filename=filename,
            extension=file_extension.lstrip("."),
            folder_id=folder_id,
            user_id=user_id,
        )

        # Get the current user from the database
        current_user = get_user_from_db(db, user_id)

        # Create the file record in the database
        new_file_db = create_file_in_db(db, file_create_schema, current_user)

        return new_file_db
    except Exception as e:
        logger.exception(f"Error creating file record: {e}")
        raise
