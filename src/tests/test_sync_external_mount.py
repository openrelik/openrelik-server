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

"""Unit tests for sync_external_mount_files_in_db (crud/file.py)."""

import os
import uuid as uuid_module

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from datastores.sql.crud.file import sync_external_mount_files_in_db
from datastores.sql.database import BaseModel
from datastores.sql.models.external_storage import ExternalStorage
from datastores.sql.models.file import File
from datastores.sql.models.folder import Folder
from datastores.sql.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_storage(mount_point):
    """Return a minimal ExternalStorage-like object."""

    class _Storage:
        name = "test_store"

    _Storage.mount_point = str(mount_point)
    return _Storage()


def _make_folder(storage_name, base_path, folder_id=1):
    """Return a minimal Folder-like object."""

    class _Folder:
        id = folder_id
        external_storage_name = storage_name
        external_base_path = base_path

    return _Folder()


def _make_user():
    class _User:
        id = 99

    return _User()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db(mocker):
    """A db session that returns an empty existing_paths set by default.

    existing_paths is collected via db.execute(...).fetchall() (Core SQL) so
    that soft-deleted records are included in the duplicate check.
    """
    db = mocker.MagicMock()
    # execute(...).fetchall() → [] (no previously registered paths)
    db.execute.return_value.fetchall.return_value = []
    return db


@pytest.fixture()
def mock_register(mocker):
    # The function is imported lazily inside sync_external_mount_files_in_db, so
    # patch its definition in the source module rather than the reference in file.py.
    return mocker.patch(
        "datastores.sql.crud.external_storage.register_external_file_in_db",
        return_value=mocker.MagicMock(),
    )


@pytest.fixture()
def mock_get_storage(mocker):
    """Patch get_external_storage_from_db in its source module (lazy import)."""
    return mocker.patch(
        "datastores.sql.crud.external_storage.get_external_storage_from_db"
    )


# ---------------------------------------------------------------------------
# Tests — flat directory (top-level files only)
# ---------------------------------------------------------------------------


def test_sync_registers_top_level_files(tmp_path, mock_db, mock_register, mock_get_storage):
    """Files directly in the base directory are registered."""
    (tmp_path / "a.bin").write_bytes(b"data")
    (tmp_path / "b.txt").write_bytes(b"data")

    storage = _make_storage(tmp_path)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", None)

    sync_external_mount_files_in_db(mock_db, folder, _make_user())

    assert mock_register.call_count == 2
    registered = {c.args[2] for c in mock_register.call_args_list}  # relative_path arg
    assert registered == {"a.bin", "b.txt"}


def test_sync_is_idempotent(tmp_path, mock_db, mock_register, mock_get_storage):
    """Already-registered paths (including soft-deleted ones) are not re-registered.

    existing_paths is now populated via db.execute(...).fetchall() (Core SQL) so
    that soft-deleted records are included.  The mock must reflect this path.
    """
    (tmp_path / "exists.bin").write_bytes(b"data")

    storage = _make_storage(tmp_path)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", None)

    # Simulate the path already being registered (Core SQL returns a list of 1-tuples)
    mock_db.execute.return_value.fetchall.return_value = [("exists.bin",)]

    sync_external_mount_files_in_db(mock_db, folder, _make_user())

    mock_register.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — recursive walk (Bug 2)
# ---------------------------------------------------------------------------


def test_sync_registers_files_in_subdirectory(
    tmp_path, mock_db, mock_register, mock_get_storage
):
    """Files nested inside subdirectories are registered with a relative path
    that includes the subdirectory prefix."""
    subdir = tmp_path / "evidence"
    subdir.mkdir()
    (subdir / "image.dd").write_bytes(b"data")

    storage = _make_storage(tmp_path)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", None)

    sync_external_mount_files_in_db(mock_db, folder, _make_user())

    assert mock_register.call_count == 1
    relative_path = mock_register.call_args.args[2]
    assert relative_path == os.path.join("evidence", "image.dd")


def test_sync_registers_deeply_nested_files(
    tmp_path, mock_db, mock_register, mock_get_storage
):
    """Files at multiple levels of nesting are all registered."""
    (tmp_path / "top.bin").write_bytes(b"data")
    level1 = tmp_path / "l1"
    level1.mkdir()
    (level1 / "mid.bin").write_bytes(b"data")
    level2 = level1 / "l2"
    level2.mkdir()
    (level2 / "deep.bin").write_bytes(b"data")

    storage = _make_storage(tmp_path)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", None)

    sync_external_mount_files_in_db(mock_db, folder, _make_user())

    assert mock_register.call_count == 3
    registered = {c.args[2] for c in mock_register.call_args_list}
    assert registered == {
        "top.bin",
        os.path.join("l1", "mid.bin"),
        os.path.join("l1", "l2", "deep.bin"),
    }


def test_sync_with_external_base_path_registers_nested_files(
    tmp_path, mock_db, mock_register, mock_get_storage
):
    """When external_base_path points to a subdirectory, nested files still get
    a relative_path relative to mount_point (not to external_base_path)."""
    base = tmp_path / "cases"
    base.mkdir()
    sub = base / "sub"
    sub.mkdir()
    (sub / "file.bin").write_bytes(b"data")

    storage = _make_storage(tmp_path)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", "cases")

    sync_external_mount_files_in_db(mock_db, folder, _make_user())

    assert mock_register.call_count == 1
    relative_path = mock_register.call_args.args[2]
    assert relative_path == os.path.join("cases", "sub", "file.bin")


def test_sync_external_base_path_excludes_files_outside_base(
    tmp_path, mock_db, mock_register, mock_get_storage
):
    """Only files under external_base_path are registered; files at the mount root
    or in sibling directories must be ignored."""
    # Files outside the base path (should NOT be registered)
    (tmp_path / "root_file.dd").write_bytes(b"data")
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    (sibling / "sibling_file.dd").write_bytes(b"data")

    # Files inside the base path (should be registered)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "inside.dd").write_bytes(b"data")
    sub = evidence / "sub"
    sub.mkdir()
    (sub / "nested.dd").write_bytes(b"data")

    storage = _make_storage(tmp_path)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", "evidence")

    sync_external_mount_files_in_db(mock_db, folder, _make_user())

    assert mock_register.call_count == 2
    registered = {c.args[2] for c in mock_register.call_args_list}
    assert registered == {
        os.path.join("evidence", "inside.dd"),
        os.path.join("evidence", "sub", "nested.dd"),
    }
    # Confirm files outside the base path were never passed to register
    assert "root_file.dd" not in registered
    assert os.path.join("sibling", "sibling_file.dd") not in registered


def test_sync_skips_symlinks(tmp_path, mock_db, mock_register, mock_get_storage):
    """Symbolic links to files are skipped."""
    real_file = tmp_path / "real.bin"
    real_file.write_bytes(b"data")
    link = tmp_path / "link.bin"
    link.symlink_to(real_file)

    storage = _make_storage(tmp_path)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", None)

    sync_external_mount_files_in_db(mock_db, folder, _make_user())

    # Only the real file should be registered, not the symlink
    assert mock_register.call_count == 1
    registered = {c.args[2] for c in mock_register.call_args_list}
    assert "real.bin" in registered
    assert "link.bin" not in registered


def test_sync_does_not_follow_symlinked_directories(
    tmp_path, mock_db, mock_register, mock_get_storage
):
    """Symbolic links to directories are not followed (followlinks=False)."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.bin").write_bytes(b"data")

    inside = tmp_path / "mount"
    inside.mkdir()
    link_dir = inside / "linked_dir"
    link_dir.symlink_to(outside)

    storage = _make_storage(inside)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", None)

    sync_external_mount_files_in_db(mock_db, folder, _make_user())

    mock_register.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — error cases
# ---------------------------------------------------------------------------


def test_sync_raises_if_storage_not_found(mock_db, mock_get_storage):
    mock_get_storage.return_value = None
    folder = _make_folder("missing_store", None)

    with pytest.raises(ValueError, match="not found"):
        sync_external_mount_files_in_db(mock_db, folder, _make_user())


def test_sync_raises_if_base_path_contains_dotdot(tmp_path, mock_db, mock_get_storage):
    """external_base_path with '..' components is rejected before realpath resolution."""
    storage = _make_storage(tmp_path / "mount")
    os.makedirs(storage.mount_point, exist_ok=True)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", "../outside")

    with pytest.raises(ValueError, match="traversal"):
        sync_external_mount_files_in_db(mock_db, folder, _make_user())


def test_sync_raises_if_base_path_escapes_mount(tmp_path, mock_db, mock_get_storage):
    """Paths that escape the mount point via symlinks are rejected after realpath."""
    mount = tmp_path / "mount"
    mount.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    # Symlink inside mount that points outside — no '..' in the name, so the
    # explicit check passes, but realpath resolves it outside the mount.
    (mount / "escape").symlink_to(outside)
    storage = _make_storage(mount)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", "escape")

    with pytest.raises(ValueError, match="escapes mount point"):
        sync_external_mount_files_in_db(mock_db, folder, _make_user())


def test_sync_raises_if_resolved_path_not_a_directory(tmp_path, mock_db, mock_get_storage):
    (tmp_path / "afile").write_bytes(b"data")
    storage = _make_storage(tmp_path)
    mock_get_storage.return_value = storage
    folder = _make_folder("test_store", "afile")  # points to a file, not a directory

    with pytest.raises(ValueError, match="not a directory"):
        sync_external_mount_files_in_db(mock_db, folder, _make_user())


# ---------------------------------------------------------------------------
# Integration test — soft-deleted duplicate prevention
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqlite_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    BaseModel.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=True)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def test_sync_does_not_create_duplicates_for_soft_deleted_paths(
    sqlite_session, tmp_path
):
    """Calling sync twice when the first record is soft-deleted must not insert
    a second record for the same path.

    The ORM query path adds WHERE is_deleted = FALSE, so soft-deleted records
    are invisible and the path would be re-registered on every sync.  The fix
    uses Core SQL which bypasses the filter and includes soft-deleted rows in
    the existing_paths set.
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

    folder = Folder(
        display_name="evidence_folder",
        uuid=uuid_module.uuid4(),
        user_id=user.id,
        external_storage_name="test_store",
        external_base_path=None,
    )
    db.add(folder)
    db.commit()

    # Create the physical file
    (tmp_path / "image.dd").write_bytes(b"\x00" * 16)

    # First sync — registers the file normally
    sync_external_mount_files_in_db(db, folder, user)

    count_after_first = db.execute(
        sa.text("SELECT COUNT(*) FROM file WHERE folder_id = :fid AND external_storage_name = 'test_store'"),
        {"fid": folder.id},
    ).scalar()
    assert count_after_first == 1

    # Soft-delete the registered record (simulates the user soft-deleting the file)
    db.execute(
        sa.text("UPDATE file SET is_deleted = 1 WHERE folder_id = :fid AND external_storage_name = 'test_store'"),
        {"fid": folder.id},
    )
    db.commit()

    # Second sync — must NOT insert a new record for the same path
    sync_external_mount_files_in_db(db, folder, user)

    count_after_second = db.execute(
        sa.text("SELECT COUNT(*) FROM file WHERE folder_id = :fid AND external_storage_name = 'test_store'"),
        {"fid": folder.id},
    ).scalar()
    assert count_after_second == 1, (
        f"Expected 1 total record (including soft-deleted), got {count_after_second}. "
        "sync must not re-register paths that are already present in a soft-deleted state."
    )
