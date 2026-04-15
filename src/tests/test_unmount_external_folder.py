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

"""Integration tests for external-mount cleanup in update_folder_in_db.

Uses an in-memory SQLite database so the full FK-safe deletion sequence can
be verified end-to-end, including the assertion that physical files survive.
"""

import uuid as uuid_module

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.v1.schemas import FolderUpdateRequest
from datastores.sql.crud.folder import update_folder_in_db
from datastores.sql.database import BaseModel
from datastores.sql.models.external_storage import ExternalStorage
from datastores.sql.models.file import File
from datastores.sql.models.folder import Folder
from datastores.sql.models.role import Role
from datastores.sql.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqlite_session():
    """Real SQLite in-memory session with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    BaseModel.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=True)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def seeded_db(sqlite_session, tmp_path):
    """Seed the DB with a user, storage, folder, one external file, and its UserRole.

    Also creates the physical file on disk so we can assert it is not deleted.

    Returns a dict with the created objects and the physical path.
    """
    db = sqlite_session

    # User
    user = User(
        username="tester",
        display_name="Tester",
        email="t@example.com",
        password_hash="x",
        auth_method="local",
        uuid=uuid_module.uuid4(),
    )
    db.add(user)
    db.flush()  # Get user.id without committing

    # ExternalStorage
    storage = ExternalStorage(
        name="test_store",
        mount_point=str(tmp_path),
        description=None,
    )
    db.add(storage)
    db.flush()

    # Folder mounted to that storage
    folder = Folder(
        display_name="evidence_folder",
        uuid=uuid_module.uuid4(),
        user_id=user.id,
        external_storage_name="test_store",
        external_base_path=None,
    )
    db.add(folder)
    db.flush()

    # Physical file on disk
    physical_file = tmp_path / "image.dd"
    physical_file.write_bytes(b"\x00" * 16)

    # Lazily-registered File record (mirrors what register_external_file_in_db creates)
    file_record = File(
        display_name="image.dd",
        uuid=uuid_module.uuid4(),
        filename="image.dd",
        filesize=16,
        extension="dd",
        data_type="file:generic",
        user_id=user.id,
        folder_id=folder.id,
        external_storage_name="test_store",
        external_relative_path="image.dd",
    )
    db.add(file_record)
    db.flush()

    # UserRole created alongside the file by register_external_file_in_db
    role = UserRole(user_id=user.id, file_id=file_record.id, role=Role.OWNER)
    db.add(role)
    db.commit()

    return {
        "db": db,
        "user": user,
        "folder": folder,
        "file_record": file_record,
        "role": role,
        "physical_file": physical_file,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_unmount_deletes_external_file_records(seeded_db):
    """When a folder is unmounted, its external File DB records are deleted."""
    db = seeded_db["db"]
    folder = seeded_db["folder"]

    # Precondition: one File record exists
    assert db.query(File).filter_by(folder_id=folder.id).count() == 1

    update_folder_in_db(db, folder.id, FolderUpdateRequest(external_storage_name=None))

    # File record must be gone from the DB
    assert db.query(File).filter_by(folder_id=folder.id).count() == 0


def test_unmount_deletes_associated_userrole(seeded_db):
    """UserRole records linked to the deleted files are removed."""
    db = seeded_db["db"]
    folder = seeded_db["folder"]
    file_id = seeded_db["file_record"].id

    # Precondition: one UserRole for this file
    assert db.query(UserRole).filter_by(file_id=file_id).count() == 1

    update_folder_in_db(db, folder.id, FolderUpdateRequest(external_storage_name=None))

    assert db.query(UserRole).filter_by(file_id=file_id).count() == 0


def test_unmount_does_not_delete_physical_file(seeded_db):
    """Physical files on disk are NOT removed when DB records are cleaned up."""
    db = seeded_db["db"]
    folder = seeded_db["folder"]
    physical_file = seeded_db["physical_file"]

    assert physical_file.exists(), "precondition: file must exist before unmount"

    update_folder_in_db(db, folder.id, FolderUpdateRequest(external_storage_name=None))

    assert physical_file.exists(), "physical file must survive DB record deletion"


def test_unmount_clears_external_storage_name_on_folder(seeded_db):
    """The folder's external_storage_name is set to None after unmounting."""
    db = seeded_db["db"]
    folder = seeded_db["folder"]

    updated = update_folder_in_db(
        db, folder.id, FolderUpdateRequest(external_storage_name=None)
    )

    assert updated.external_storage_name is None


def test_no_deletion_when_not_unmounting(seeded_db):
    """Updating display_name only must not delete any File records."""
    db = seeded_db["db"]
    folder = seeded_db["folder"]

    update_folder_in_db(db, folder.id, FolderUpdateRequest(display_name="renamed"))

    # File record must still be present
    assert db.query(File).filter_by(folder_id=folder.id).count() == 1


def test_unmount_is_idempotent(seeded_db):
    """Calling unmount twice must not raise and must leave 0 File records."""
    db = seeded_db["db"]
    folder = seeded_db["folder"]

    update_folder_in_db(db, folder.id, FolderUpdateRequest(external_storage_name=None))
    # Second call — folder already has external_storage_name=None; no files to delete
    update_folder_in_db(db, folder.id, FolderUpdateRequest(external_storage_name=None))

    assert db.query(File).filter_by(folder_id=folder.id).count() == 0


def test_unmount_clears_external_base_path_even_when_not_in_request(sqlite_session, tmp_path):
    """Unmounting by sending only external_storage_name=null must also clear
    external_base_path, even if it was not included in the request body.

    Regression: previously the CRUD only updated fields present in model_fields_set,
    so a stale external_base_path would remain after unmounting.
    """
    db = sqlite_session

    user = User(
        username="tester2",
        display_name="Tester2",
        email="t2@example.com",
        password_hash="x",
        auth_method="local",
        uuid=uuid_module.uuid4(),
    )
    db.add(user)
    db.flush()

    storage = ExternalStorage(
        name="store2",
        mount_point=str(tmp_path),
        description=None,
    )
    db.add(storage)
    db.flush()

    folder = Folder(
        display_name="folder2",
        uuid=uuid_module.uuid4(),
        user_id=user.id,
        external_storage_name="store2",
        external_base_path="cases/2024",  # non-null base path
    )
    db.add(folder)
    db.commit()

    # Send only external_storage_name=null — external_base_path is NOT in the request.
    request = FolderUpdateRequest(external_storage_name=None)
    assert "external_base_path" not in request.model_fields_set

    updated = update_folder_in_db(db, folder.id, request)

    assert updated.external_storage_name is None
    assert updated.external_base_path is None, (
        "external_base_path must be cleared when external_storage_name is set to null, "
        "even if external_base_path was not explicitly included in the request."
    )
