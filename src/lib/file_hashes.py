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
