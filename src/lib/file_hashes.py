# Copyright 2024-2025 Google LLC
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

import hashlib

from datastores.sql import database
from datastores.sql.crud.file import get_file_from_db


def _calculate_file_hashes(file_path):
    """
    Calculates MD5, SHA1, and SHA256 hashes for a given file path.

    Args:
        file_path (str): The path to the file.

    Returns:
        tuple: A tuple containing the MD5, SHA1, and SHA256 hashes as strings.
    """
    # Initialize hash objects
    md5_hash = hashlib.md5()
    sha1_hash = hashlib.sha1()
    sha256_hash = hashlib.sha256()

    # Define a chunk size for efficient reading
    CHUNK_SIZE = 4096

    # Read the file in chunks and update the hash objects
    with open(file_path, "rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            md5_hash.update(chunk)
            sha1_hash.update(chunk)
            sha256_hash.update(chunk)

    return (md5_hash.hexdigest(), sha1_hash.hexdigest(), sha256_hash.hexdigest())


def generate_hashes(file_id):
    """Generates MD5, SHA1, and SHA256 hashes for a file and updates the database.

    Args:
        file_id (int): The ID of the file in the database.
    """
    db = database.SessionLocal()
    file = get_file_from_db(db, file_id)

    # Calculate the hashes for the file.
    md5_hash, sha1_hash, sha256_hash = _calculate_file_hashes(file.path)

    # Update the file database record with the calculated hashes.
    file.hash_md5 = md5_hash
    file.hash_sha1 = sha1_hash
    file.hash_sha256 = sha256_hash

    # Commit the changes to the database
    db.commit()
