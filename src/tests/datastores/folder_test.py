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

import re
import uuid
import warnings

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from datastores.sql.crud.folder import (
    get_root_folders_from_db,
    get_subfolders_from_db,
    get_folder_from_db,
    create_root_folder_in_db,
    get_shared_folders_from_db,
    get_all_folders_from_db,
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
    folders["shared_sub"] = new_folder("shared_sub", other, parent=folders["other_root"])
    db.flush()

    db.add_all(
        [
            UserRole(user=me, folder=folders["user_shared"], role=Role.VIEWER),
            UserRole(user=me, folder=folders["deleted_shared"], role=Role.VIEWER),
            UserRole(user=me, folder=folders["shared_sub"], role=Role.EDITOR),
            UserRole(user=me, folder=folders["shared_and_owned"], role=Role.VIEWER),
            UserRole(user=me, folder=folders["shared_and_owned"], role=Role.OWNER),
            # File-level role, folder_id is NULL. Must not break NOT IN subqueries.
            UserRole(user=me, folder_id=None, role=Role.VIEWER),
            GroupRole(group=group, folder=folders["group_shared"], role=Role.VIEWER),
        ]
    )
    db.commit()
    return me, folders


def _names(folders):
    return {folder.display_name for folder in folders}


def _count_queries(db):
    """Return a list that collects every SQL statement executed on the session's engine."""
    statements = []
    event.listen(
        db.get_bind(),
        "before_cursor_execute",
        lambda conn, cursor, statement, *args: statements.append(statement),
    )
    return statements


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

    folders, total = get_all_folders_from_db(sqlite_db, me)

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

    folders, total = get_all_folders_from_db(sqlite_db, me, search_term="sub")

    assert _names(folders) == {"my_sub", "shared_sub"}
    assert total == 2


def test_get_all_folders_from_db_pagination(folder_tree, sqlite_db):
    """Test that paging returns every folder exactly once."""
    me, _ = folder_tree

    seen = []
    for page in range(1, 4):
        folders, total = get_all_folders_from_db(sqlite_db, me, page=page, page_size=2)
        seen.extend(folder.id for folder in folders)

    assert total == 5
    assert len(seen) == len(set(seen)) == total


@pytest.mark.parametrize(
    "list_folders",
    [
        get_root_folders_from_db,
        get_shared_folders_from_db,
        lambda db, user: get_all_folders_from_db(db, user)[0],
        lambda db, user: get_all_folders_from_db(db, user, search_term="sub")[0],
    ],
)
def test_folder_listing_query_count(folder_tree, sqlite_db, list_folders):
    """Folder listings must not cross join or lazy load per folder (N+1)."""
    me, _ = folder_tree
    # Drop cached relationships so lazy loads would hit the database, then reload the user.
    sqlite_db.expire_all()
    sqlite_db.refresh(me)
    statements = _count_queries(sqlite_db)

    with warnings.catch_warnings():
        # SQLAlchemy warns about cartesian products, fail the test if that happens.
        warnings.simplefilter("error")
        folders = list_folders(sqlite_db, me)
        response = [schemas.FolderResponseCompact.model_validate(folder) for folder in folders]

    assert response
    assert all(folder.workflows for folder in response)
    # Folder query (+ count) + one query each for eager loading users and workflows.
    assert len(statements) <= 4
    # Workflows must be loaded in one batch, not one lazy load per folder.
    assert sum("FROM workflow" in statement for statement in statements) == 1
    # No implicit cross join, e.g. "FROM (...) AS anon_1, folder WHERE ...".
    assert not any(re.search(r",\s*folder\s+WHERE", statement) for statement in statements)


def test_get_subfolders_from_db(db):
    """Test get_subfolders_from_db."""
    parent_id = 1
    mock_query = db.query.return_value
    mock_filter = mock_query.filter_by.return_value
    mock_order = mock_filter.order_by.return_value
    mock_order.all.return_value = [Folder(id=2, parent_id=parent_id)]

    result = get_subfolders_from_db(db, parent_id)

    db.query.assert_called_once_with(Folder)
    mock_query.filter_by.assert_called_once_with(parent_id=parent_id)
    assert len(result) == 1
    assert result[0].id == 2


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
