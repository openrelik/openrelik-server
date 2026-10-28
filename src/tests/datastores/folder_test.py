# Copyright 2026 Google LLC
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

"""Tests for folder CRUD operations."""

import base64
import contextlib
import datetime
import json
import re
import uuid
import warnings

import pytest
from sqlalchemy import create_engine, event, update
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from datastores.sql.crud.folder import (
    get_root_folders_from_db,
    get_subfolders_from_db,
    get_folder_from_db,
    create_root_folder_in_db,
    get_shared_folders_from_db,
    get_all_folders_from_db,
    InvalidCursorError,
    create_subfolder_in_db,
    delete_folder_from_db,
)
from datastores.sql.database import BaseModel
from datastores.sql.models.folder import Folder
from datastores.sql.models.group import Group, GroupRole
from datastores.sql.models.role import Role
from datastores.sql.models.user import User, UserRole
from datastores.sql.models.workflow import Workflow
from api.v1 import schemas


@pytest.fixture
def sqlite_db():
    """Real in-memory SQLite session, for tests that need to execute the generated SQL."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    BaseModel.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def folder_tree(sqlite_db):
    """Users, groups and folders covering owned, shared, group-shared and deleted folders."""
    db = sqlite_db

    def new_user(name):
        return User(display_name=name, username=name, auth_method="local", uuid=uuid.uuid4())

    me, other = new_user("me"), new_user("other")
    group = Group(name="group", uuid=uuid.uuid4(), users=[me])
    db.add_all([me, other, group])
    db.flush()

    def new_folder(name, owner, parent=None, deleted=False):
        folder = Folder(
            display_name=name, uuid=uuid.uuid4(), user=owner, parent=parent, is_deleted=deleted
        )
        db.add(folder)
        db.add(UserRole(user=owner, folder=folder, role=Role.OWNER))
        db.add(Workflow(display_name=f"{name}-workflow", uuid=uuid.uuid4(), user=owner, folder=folder))
        return folder

    folders = {
        "my_root": new_folder("my_root", me),
        "my_deleted_root": new_folder("my_deleted_root", me, deleted=True),
        "other_root": new_folder("other_root", other),
        "user_shared": new_folder("user_shared", other),
        "group_shared": new_folder("group_shared", other),
        "deleted_shared": new_folder("deleted_shared", other, deleted=True),
        "shared_and_owned": new_folder("shared_and_owned", other),
    }
    folders["my_sub"] = new_folder("my_sub", me, parent=folders["my_root"])
    folders["my_child"] = new_folder("my_child", me, parent=folders["my_root"])
    folders["shared_sub"] = new_folder("shared_sub", other, parent=folders["other_root"])
    db.flush()

    db.add_all(
        [
            UserRole(user=me, folder=folders["user_shared"], role=Role.VIEWER),
            UserRole(user=me, folder=folders["deleted_shared"], role=Role.VIEWER),
            UserRole(user=me, folder=folders["shared_sub"], role=Role.EDITOR),
            UserRole(user=me, folder=folders["shared_and_owned"], role=Role.VIEWER),
            UserRole(user=me, folder=folders["shared_and_owned"], role=Role.OWNER),
            # File-level role, folder_id is NULL. Must not show up in the folder ID subqueries.
            UserRole(user=me, folder_id=None, role=Role.VIEWER),
            GroupRole(group=group, folder=folders["group_shared"], role=Role.VIEWER),
        ]
    )
    db.commit()
    return me, folders


def _names(folders):
    return {folder.display_name for folder in folders}


@contextlib.contextmanager
def _count_queries(db):
    """Collect every SQL statement executed on the session's engine inside the block."""
    statements = []

    def _record(conn, cursor, statement, *args):
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _record)


def test_get_root_folders_from_db(folder_tree, sqlite_db):
    """Test get_root_folders_from_db."""
    me, _ = folder_tree

    result = get_root_folders_from_db(sqlite_db, me)

    assert _names(result) == {"my_root", "shared_and_owned"}


def test_get_shared_folders_from_db(folder_tree, sqlite_db):
    """Test get_shared_folders_from_db excludes owned and deleted folders."""
    me, _ = folder_tree

    result = get_shared_folders_from_db(sqlite_db, me)

    assert _names(result) == {"user_shared", "group_shared", "shared_sub"}


def test_get_all_folders_from_db_default(folder_tree, sqlite_db):
    """Test get_all_folders_from_db in default mode (no search)."""
    me, _ = folder_tree

    folders, total, next_cursor = get_all_folders_from_db(sqlite_db, me)

    assert next_cursor is None
    assert _names(folders) == {
        "my_root",
        "shared_and_owned",
        "user_shared",
        "group_shared",
        "shared_sub",
    }
    assert total == 5


def test_get_all_folders_from_db_search(folder_tree, sqlite_db):
    """Test get_all_folders_from_db in search mode includes inherited subfolders."""
    me, _ = folder_tree

    folders, total, _ = get_all_folders_from_db(sqlite_db, me, search_term="sub")

    assert _names(folders) == {"my_sub", "shared_sub"}
    assert total == 2


def test_get_all_folders_from_db_pagination(folder_tree, sqlite_db):
    """Test that paging returns every folder exactly once, in a stable order."""
    me, _ = folder_tree
    # Give all folders the same created_at so the order depends on the id tie-breaker.
    sqlite_db.execute(update(Folder).values(created_at=datetime.datetime(2026, 1, 1)))
    sqlite_db.commit()

    seen = []
    for page in range(1, 4):
        folders, total, _ = get_all_folders_from_db(sqlite_db, me, page=page, page_size=2)
        seen.extend(folder.id for folder in folders)

    assert total == 5
    assert len(seen) == len(set(seen)) == total
    assert seen == sorted(seen, reverse=True)


def _set_times(db, folders, updated=None, created=None):
    """Set updated_at and created_at of the named folders, and of the others to 2025-01-01.

    Both columns are set in each update, as any update sets updated_at to now(). Also, in
    SQLite, timestamps from now() don't compare correctly with bound datetimes (they're
    compared as strings in different formats).
    """
    base = datetime.datetime(2025, 1, 1)
    db.execute(update(Folder).values(updated_at=base, created_at=base))
    for name in set(updated or {}) | set(created or {}):
        values = {
            "updated_at": (updated or {}).get(name, base),
            "created_at": (created or {}).get(name, base),
        }
        db.execute(update(Folder).where(Folder.id == folders[name].id).values(values))
    db.commit()


def _walk(db, user, page_size, **kwargs):
    """Follow next_cursor from the first page to the end, returning the folders in order."""
    folders, total, next_cursor = get_all_folders_from_db(db, user, page_size=page_size, **kwargs)
    pages = 1
    while next_cursor:
        assert pages < 20, "cursor doesn't advance"
        page, page_total, next_cursor = get_all_folders_from_db(
            db, user, page_size=page_size, after=next_cursor, **kwargs
        )
        assert page_total is None, "requests with a cursor must not count"
        folders.extend(page)
        pages += 1
    return folders, total, pages


@pytest.mark.parametrize(
    "sort, order, expected",
    [
        (
            "updated_at",
            "asc",
            ["shared_sub", "user_shared", "my_root", "group_shared", "shared_and_owned"],
        ),
        (
            "updated_at",
            "desc",
            ["shared_and_owned", "group_shared", "my_root", "user_shared", "shared_sub"],
        ),
        (
            "display_name",
            "asc",
            ["group_shared", "my_root", "shared_and_owned", "shared_sub", "user_shared"],
        ),
        (
            "created_at",
            "desc",
            ["shared_and_owned", "group_shared", "user_shared", "my_root", "shared_sub"],
        ),
    ],
)
@pytest.mark.parametrize("page_size", [1, 2, 5, 100])
def test_get_all_folders_from_db_sort_and_cursor(
    folder_tree, sqlite_db, sort, order, expected, page_size
):
    """Cursor paging returns every folder once, in the requested order."""
    me, folders = folder_tree
    day = lambda d: datetime.datetime(2026, 1, d)
    # Names sort case-insensitively. Renamed before setting the times, as updates set
    # updated_at.
    sqlite_db.execute(
        update(Folder).where(Folder.id == folders["my_root"].id).values(display_name="My_root")
    )
    # my_root and group_shared share an update time, so the id breaks the tie.
    _set_times(
        sqlite_db,
        folders,
        updated={
            "shared_sub": day(1),
            "user_shared": day(2),
            "my_root": day(3),
            "group_shared": day(3),
            "shared_and_owned": day(4),
        },
        created={
            "shared_sub": day(1),
            "my_root": day(2),
            "user_shared": day(3),
            "group_shared": day(4),
            "shared_and_owned": day(5),
        },
    )
    expected = ["My_root" if name == "my_root" else name for name in expected]

    listed, total, pages = _walk(sqlite_db, me, page_size, sort=sort, order=order)

    assert total == 5
    assert [folder.display_name for folder in listed] == expected
    assert pages == -(-5 // page_size)


def test_get_all_folders_from_db_cursor_is_stable(folder_tree, sqlite_db):
    """Folders created while paging don't shift or repeat the remaining folders."""
    me, folders = folder_tree
    _set_times(sqlite_db, folders)
    first, total, next_cursor = get_all_folders_from_db(sqlite_db, me, page_size=2)
    new = Folder(
        display_name="new_root",
        uuid=uuid.uuid4(),
        user=me,
        created_at=datetime.datetime(2026, 1, 1),
    )
    sqlite_db.add_all([new, UserRole(user=me, folder=new, role=Role.OWNER)])
    sqlite_db.commit()

    rest = []
    while next_cursor:
        assert len(rest) < 20, "cursor doesn't advance"
        page, _, next_cursor = get_all_folders_from_db(
            sqlite_db, me, page_size=2, after=next_cursor
        )
        rest.extend(page)

    ids = [folder.id for folder in first + rest]
    assert len(ids) == len(set(ids)) == total
    # The newest folder sorts first, before the cursor, so it isn't returned.
    assert new.id not in ids


@pytest.mark.parametrize(
    "cursor",
    ["not base64!", "e30=", "bm90IGpzb24="],
    ids=["garbled", "empty object", "not json"],
)
def test_get_all_folders_from_db_invalid_cursor(folder_tree, sqlite_db, cursor):
    """Malformed cursors are rejected."""
    me, _ = folder_tree
    with pytest.raises(InvalidCursorError):
        get_all_folders_from_db(sqlite_db, me, after=cursor)


def test_get_all_folders_from_db_cursor_for_other_sort(folder_tree, sqlite_db):
    """A cursor can only continue the listing it came from."""
    me, folders = folder_tree
    _set_times(sqlite_db, folders)
    _, _, next_cursor = get_all_folders_from_db(sqlite_db, me, page_size=1, sort="updated_at")
    with pytest.raises(InvalidCursorError):
        get_all_folders_from_db(sqlite_db, me, page_size=1, sort="display_name", after=next_cursor)
    with pytest.raises(InvalidCursorError):
        get_all_folders_from_db(
            sqlite_db, me, page_size=1, sort="updated_at", order="asc", after=next_cursor
        )


def _cursor(**payload):
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


@pytest.mark.parametrize(
    "sort, payload",
    [
        ("display_name", {"value": 5, "id": 1}),
        ("display_name", {"value": None, "id": 1}),
        ("updated_at", {"value": "yesterday", "id": 1}),
        ("display_name", {"value": "a", "id": "1"}),
        ("display_name", {"value": "a", "id": True}),
        ("display_name", {"value": "a", "id": 1.5}),
        ("display_name", {"value": "a", "id": 0}),
        ("display_name", {"value": "a", "id": 2**63}),
    ],
    ids=[
        "name not a string",
        "name null",
        "time not a timestamp",
        "id a string",
        "id a bool",
        "id a float",
        "id zero",
        "id too large",
    ],
)
def test_get_all_folders_from_db_tampered_cursor(folder_tree, sqlite_db, sort, payload):
    """Well-formed cursors with values of the wrong type or range are rejected."""
    me, _ = folder_tree
    cursor = _cursor(sort=sort, order="desc", q=None, **payload)
    with pytest.raises(InvalidCursorError):
        get_all_folders_from_db(sqlite_db, me, sort=sort, after=cursor)


def test_get_all_folders_from_db_cursor_for_other_search(folder_tree, sqlite_db):
    """A cursor from a listing can't continue a search, or another search, and back."""
    me, folders = folder_tree
    _set_times(sqlite_db, folders)
    _, _, listing_cursor = get_all_folders_from_db(sqlite_db, me, page_size=1)
    _, _, search_cursor = get_all_folders_from_db(sqlite_db, me, page_size=1, search_term="sub")
    for search_term, cursor in [
        ("sub", listing_cursor),
        (None, search_cursor),
        ("my", search_cursor),
    ]:
        with pytest.raises(InvalidCursorError):
            get_all_folders_from_db(
                sqlite_db, me, page_size=1, search_term=search_term, after=cursor
            )


@pytest.mark.parametrize(
    "kwargs",
    [{"sort": "user_id"}, {"order": "ASC"}, {"page": 0}, {"page": -1}, {"page_size": -1}],
)
def test_get_all_folders_from_db_unsupported_sort(folder_tree, sqlite_db, kwargs):
    """Only the documented sort keys and orders, and valid pages, are accepted."""
    me, _ = folder_tree
    with pytest.raises(ValueError):
        get_all_folders_from_db(sqlite_db, me, **kwargs)


def test_get_all_folders_from_db_zero_page_size(folder_tree, sqlite_db):
    """A page size of zero returns no folders and no cursor, as before cursors."""
    me, _ = folder_tree

    folders, total, next_cursor = get_all_folders_from_db(sqlite_db, me, page_size=0)

    assert folders == []
    assert total == 5
    assert next_cursor is None


def test_get_all_folders_from_db_search_with_cursor(folder_tree, sqlite_db):
    """Cursor paging also works for searches."""
    me, _ = folder_tree

    listed, total, pages = _walk(
        sqlite_db, me, 1, search_term="sub", sort="display_name", order="asc"
    )

    assert total == 2
    assert [folder.display_name for folder in listed] == ["my_sub", "shared_sub"]
    assert pages == 2


@pytest.mark.parametrize(
    "list_folders",
    [
        lambda db, user, folders: get_root_folders_from_db(db, user),
        lambda db, user, folders: get_shared_folders_from_db(db, user),
        lambda db, user, folders: get_all_folders_from_db(db, user)[0],
        lambda db, user, folders: get_all_folders_from_db(db, user, search_term="sub")[0],
        lambda db, user, folders: get_subfolders_from_db(db, folders["my_root"].id),
    ],
    ids=["root", "shared", "all", "all_search", "subfolders"],
)
def test_folder_listing_query_count(folder_tree, sqlite_db, list_folders):
    """Folder listings must not cross join or lazy load per folder (N+1)."""
    me, folders = folder_tree
    # Drop cached relationships so lazy loads would hit the database, then reload the objects
    # used to build the query so that doesn't count either.
    sqlite_db.expire_all()
    sqlite_db.refresh(me)
    sqlite_db.refresh(folders["my_root"])
    with _count_queries(sqlite_db) as statements, warnings.catch_warnings():
        # SQLAlchemy warns about cartesian products, fail the test if that happens. Only
        # SQLAlchemy warnings, so unrelated deprecation warnings don't fail the test.
        warnings.simplefilter("error", category=SAWarning)
        listed = list_folders(sqlite_db, me, folders)
        response = [schemas.FolderResponseCompact.model_validate(folder) for folder in listed]

    assert response
    assert all(folder.workflows for folder in response)
    # Folder query (+ count) + one query each for eager loading users and workflows.
    assert len(statements) <= 4
    # Workflows must be loaded in one batch, not one lazy load per folder.
    assert sum("FROM workflow" in statement for statement in statements) == 1
    # No implicit cross join, e.g. "FROM (...) AS anon_1, folder WHERE ...".
    assert not any(re.search(r",\s*folder\s+WHERE", statement) for statement in statements)


def test_get_subfolders_from_db(folder_tree, sqlite_db):
    """Test get_subfolders_from_db returns direct children, newest first."""
    _, folders = folder_tree

    result = get_subfolders_from_db(sqlite_db, folders["my_root"].id)

    assert [folder.display_name for folder in result] == ["my_child", "my_sub"]


def test_get_folder_from_db(db):
    """Test get_folder_from_db."""
    folder_id = 1
    db.get.return_value = Folder(id=folder_id)

    result = get_folder_from_db(db, folder_id)

    db.get.assert_called_once_with(Folder, folder_id)
    assert result.id == folder_id


def test_create_root_folder_in_db(mocker, db):
    """Test create_root_folder_in_db."""
    mock_config = mocker.patch("datastores.sql.crud.folder.config")
    mock_os = mocker.patch("datastores.sql.crud.folder.os")

    current_user = User(id=1)
    new_folder = schemas.FolderCreateRequest(display_name="New Folder")

    mock_config.get.return_value.get.return_value.get.return_value = {
        "default": "default_provider"
    }
    mock_os.path.exists.return_value = False

    result = create_root_folder_in_db(db, new_folder, current_user)

    db.add.assert_called()
    db.commit.assert_called()
    db.refresh.assert_called()
    mock_os.mkdir.assert_called_once()
    assert result.display_name == "New Folder"


def test_create_subfolder_in_db(mocker, db):
    """Test create_subfolder_in_db."""
    mock_config = mocker.patch("datastores.sql.crud.folder.config")
    mock_get_folder = mocker.patch("datastores.sql.crud.folder.get_folder_from_db")
    mock_os = mocker.patch("datastores.sql.crud.folder.os")

    current_user = User(id=1)
    parent_folder = Folder(id=1, uuid=uuid.uuid4())
    mock_get_folder.return_value = parent_folder

    new_folder = schemas.FolderCreateRequest(display_name="Subfolder")

    mock_config.get.return_value.get.return_value.get.return_value = {
        "default": "default_provider"
    }
    mock_os.path.exists.return_value = False

    result = create_subfolder_in_db(
        db, folder_id=1, new_folder=new_folder, current_user=current_user
    )

    db.add.assert_called()
    db.commit.assert_called()
    mock_os.mkdir.assert_called_once()
    assert result.display_name == "Subfolder"


def test_delete_folder_from_db(db):
    """Test delete_folder_from_db."""
    folder_id = 1

    mock_execute = db.execute.return_value
    mock_scalars = mock_execute.scalars.return_value
    mock_scalars.all.return_value = [1, 2, 3]  # Folder IDs

    delete_folder_from_db(db, folder_id)

    assert db.execute.call_count == 3
    db.commit.assert_called_once()


def test_delete_folder_from_db_empty(db):
    """Test delete_folder_from_db when no folders found."""
    folder_id = 1

    mock_execute = db.execute.return_value
    mock_scalars = mock_execute.scalars.return_value
    mock_scalars.all.return_value = []

    delete_folder_from_db(db, folder_id)

    assert db.execute.call_count == 1
    db.commit.assert_not_called()
