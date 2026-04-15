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

"""Integration tests for delete_external_storage_from_db cascade behaviour.

Uses an in-memory SQLite database so the full FK-safe deletion sequence can
be verified end-to-end, including:
  - File records are deleted from the DB
  - Folders are unmounted (external_storage_name set to NULL)
  - UserRole rows for affected files are removed
  - Physical files on disk are NOT removed
  - The ExternalStorage record itself is removed
"""

import uuid as uuid_module

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from datastores.sql.crud.external_storage import delete_external_storage_from_db
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
    """Seed the DB with a user, storage, two folders, two files, and their UserRoles.

    Folder layout:
      folder_a  — mounted to test_store / base_a (has file_a)
      folder_b  — mounted to test_store / (no base_path) (has file_b)

    Physical files are created on disk so we can assert they survive.

    Returns a dict with the created objects and physical paths.
    """
    db = sqlite_session

    user = User(
        username="tester",
        display_name="Tester",
        email="t@example.com",
        password_hash="x",
        auth_method="local",
        uuid=uuid_module.uuid4(),
    )
    db.add(user)
    db.flush()

    storage = ExternalStorage(
        name="test_store",
        mount_point=str(tmp_path),
        description=None,
    )
    db.add(storage)
    db.flush()

    # Folder A — mounted with a base path
    base_a = tmp_path / "base_a"
    base_a.mkdir()
    folder_a = Folder(
        display_name="folder_a",
        uuid=uuid_module.uuid4(),
        user_id=user.id,
        external_storage_name="test_store",
        external_base_path="base_a",
    )
    db.add(folder_a)
    db.flush()

    physical_a = base_a / "image_a.dd"
    physical_a.write_bytes(b"\x00" * 16)

    file_a = File(
        display_name="image_a.dd",
        uuid=uuid_module.uuid4(),
        filename="image_a.dd",
        filesize=16,
        extension="dd",
        data_type="file:generic",
        user_id=user.id,
        folder_id=folder_a.id,
        external_storage_name="test_store",
        external_relative_path="base_a/image_a.dd",
    )
    db.add(file_a)
    db.flush()

    role_a = UserRole(user_id=user.id, file_id=file_a.id, role=Role.OWNER)
    db.add(role_a)

    # Folder B — mounted at root of storage
    folder_b = Folder(
        display_name="folder_b",
        uuid=uuid_module.uuid4(),
        user_id=user.id,
        external_storage_name="test_store",
        external_base_path=None,
    )
    db.add(folder_b)
    db.flush()

    physical_b = tmp_path / "image_b.dd"
    physical_b.write_bytes(b"\x00" * 32)

    file_b = File(
        display_name="image_b.dd",
        uuid=uuid_module.uuid4(),
        filename="image_b.dd",
        filesize=32,
        extension="dd",
        data_type="file:generic",
        user_id=user.id,
        folder_id=folder_b.id,
        external_storage_name="test_store",
        external_relative_path="image_b.dd",
    )
    db.add(file_b)
    db.flush()

    role_b = UserRole(user_id=user.id, file_id=file_b.id, role=Role.OWNER)
    db.add(role_b)

    db.commit()

    return {
        "db": db,
        "user": user,
        "storage": storage,
        "folder_a": folder_a,
        "folder_b": folder_b,
        "file_a": file_a,
        "file_b": file_b,
        "role_a": role_a,
        "role_b": role_b,
        "physical_a": physical_a,
        "physical_b": physical_b,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_delete_storage_removes_storage_record(seeded_db):
    """The ExternalStorage record is deleted from the DB."""
    db = seeded_db["db"]
    storage = seeded_db["storage"]

    assert db.query(ExternalStorage).filter_by(name="test_store").count() == 1

    delete_external_storage_from_db(db, storage)

    assert db.query(ExternalStorage).filter_by(name="test_store").count() == 0


def test_delete_storage_removes_file_records(seeded_db):
    """All File DB records referencing the storage are deleted."""
    db = seeded_db["db"]
    storage = seeded_db["storage"]

    assert db.query(File).filter_by(external_storage_name="test_store").count() == 2

    delete_external_storage_from_db(db, storage)

    assert db.query(File).filter_by(external_storage_name="test_store").count() == 0


def test_delete_storage_removes_userrole_records(seeded_db):
    """UserRole rows for the deleted files are removed."""
    db = seeded_db["db"]
    storage = seeded_db["storage"]
    file_a_id = seeded_db["file_a"].id
    file_b_id = seeded_db["file_b"].id

    assert db.query(UserRole).filter(UserRole.file_id.in_([file_a_id, file_b_id])).count() == 2

    delete_external_storage_from_db(db, storage)

    assert db.query(UserRole).filter(UserRole.file_id.in_([file_a_id, file_b_id])).count() == 0


def test_delete_storage_unmounts_folders(seeded_db):
    """All folders mounted to the storage are unmounted (external_storage_name set to NULL)."""
    db = seeded_db["db"]
    storage = seeded_db["storage"]
    folder_a_id = seeded_db["folder_a"].id
    folder_b_id = seeded_db["folder_b"].id

    delete_external_storage_from_db(db, storage)

    db.expire_all()
    folder_a = db.get(Folder, folder_a_id)
    folder_b = db.get(Folder, folder_b_id)
    assert folder_a.external_storage_name is None
    assert folder_a.external_base_path is None
    assert folder_b.external_storage_name is None
    assert folder_b.external_base_path is None


def test_delete_storage_does_not_delete_physical_files(seeded_db):
    """Physical files on disk are NOT removed when the storage is deleted."""
    db = seeded_db["db"]
    storage = seeded_db["storage"]
    physical_a = seeded_db["physical_a"]
    physical_b = seeded_db["physical_b"]

    assert physical_a.exists(), "precondition: file_a must exist"
    assert physical_b.exists(), "precondition: file_b must exist"

    delete_external_storage_from_db(db, storage)

    assert physical_a.exists(), "physical_a must survive storage deletion"
    assert physical_b.exists(), "physical_b must survive storage deletion"


def test_delete_storage_with_no_references_succeeds(sqlite_session):
    """Deleting a storage that has no file/folder references works without error."""
    db = sqlite_session

    storage = ExternalStorage(
        name="empty_store",
        mount_point="/mnt/empty",
        description=None,
    )
    db.add(storage)
    db.commit()

    result = delete_external_storage_from_db(db, storage)

    assert result is True
    assert db.query(ExternalStorage).filter_by(name="empty_store").count() == 0


def test_delete_storage_returns_true(seeded_db):
    """delete_external_storage_from_db always returns True."""
    db = seeded_db["db"]
    storage = seeded_db["storage"]

    result = delete_external_storage_from_db(db, storage)

    assert result is True


def test_delete_storage_removes_soft_deleted_file_records(sqlite_session, tmp_path):
    """Files with is_deleted=True are also removed (Core SQL bypasses soft-delete filter)."""
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
        name="soft_store",
        mount_point=str(tmp_path),
        description=None,
    )
    db.add(storage)
    db.flush()

    folder = Folder(
        display_name="folder",
        uuid=uuid_module.uuid4(),
        user_id=user.id,
        external_storage_name="soft_store",
        external_base_path=None,
    )
    db.add(folder)
    db.flush()

    # Create a file that is already soft-deleted
    soft_file = File(
        display_name="ghost.dd",
        uuid=uuid_module.uuid4(),
        filename="ghost.dd",
        filesize=8,
        extension="dd",
        data_type="file:generic",
        user_id=user.id,
        folder_id=folder.id,
        external_storage_name="soft_store",
        external_relative_path="ghost.dd",
        is_deleted=True,
    )
    db.add(soft_file)
    db.commit()

    # Precondition: the file exists in the DB (ORM query won't see it due to
    # the soft-delete filter, but the raw count should show 1)
    from sqlalchemy import text
    raw_count = db.execute(
        text("SELECT COUNT(*) FROM file WHERE external_storage_name = 'soft_store'")
    ).scalar()
    assert raw_count == 1

    delete_external_storage_from_db(db, storage)

    # The file must be gone from the DB entirely
    raw_count_after = db.execute(
        text("SELECT COUNT(*) FROM file WHERE external_storage_name = 'soft_store'")
    ).scalar()
    assert raw_count_after == 0
