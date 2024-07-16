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

from datastores.sql import database
from datastores.sql.crud.file import get_file_from_db

import hashlib


def generate_hashes(file_id):
    db = database.SessionLocal()
    file = get_file_from_db(db, file_id)
    with open(file.path, "rb") as fh:
        md5 = hashlib.file_digest(fh, "md5").hexdigest()
        sha1 = hashlib.file_digest(fh, "sha1").hexdigest()
        sha256 = hashlib.file_digest(fh, "sha256").hexdigest()
    file.hash_md5 = md5
    file.hash_sha1 = sha1
    file.hash_sha256 = sha256
    db.commit()
