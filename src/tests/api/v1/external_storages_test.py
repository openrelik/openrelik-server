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

"""Tests for external storage CRUD and file registration endpoints."""

import uuid

import pytest

from datastores.sql.models.external_storage import ExternalStorage
from datastores.sql.models.file import File


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage(name="test_store", mount_point="/mnt/cases") -> ExternalStorage:
    return ExternalStorage(
        id=1,
        name=name,
        mount_point=mount_point,
        description="Test storage",
        created_at=None,
        updated_at=None,
        deleted_at=None,
        is_deleted=False,
    )


def _storage_dict(name="test_store", mount_point="/mnt/cases"):
    return {
        "id": 1,
        "name": name,
        "mount_point": mount_point,
        "description": "Test storage",
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "is_deleted": False,
    }


# ---------------------------------------------------------------------------
# GET /datastores/
# ---------------------------------------------------------------------------

def test_list_external_storages(fastapi_test_client, mocker):
    mock_list = mocker.patch("api.v1.external_storages.get_external_storages_from_db")
    mock_list.return_value = [_make_storage()]

    response = fastapi_test_client.get("/datastores/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "test_store"


# ---------------------------------------------------------------------------
# POST /datastores/
# ---------------------------------------------------------------------------

def test_create_external_storage_success(fastapi_test_client, mocker):
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db", return_value=None
    )
    mock_create = mocker.patch("api.v1.external_storages.create_external_storage_in_db")
    mock_create.return_value = _make_storage()

    response = fastapi_test_client.post(
        "/datastores/",
        json={"name": "test_store", "mount_point": "/mnt/cases", "description": "Test storage"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "test_store"


def test_create_external_storage_conflict(fastapi_test_client, mocker):
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=_make_storage(),
    )
    response = fastapi_test_client.post(
        "/datastores/",
        json={"name": "test_store", "mount_point": "/mnt/cases"},
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# GET /datastores/{storage_name}
# ---------------------------------------------------------------------------

def test_get_external_storage_found(fastapi_test_client, mocker):
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=_make_storage(),
    )
    response = fastapi_test_client.get("/datastores/test_store")
    assert response.status_code == 200
    assert response.json()["name"] == "test_store"


def test_get_external_storage_not_found(fastapi_test_client, mocker):
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db", return_value=None
    )
    response = fastapi_test_client.get("/datastores/nonexistent")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /datastores/{storage_name}
# ---------------------------------------------------------------------------

def test_update_external_storage_success(fastapi_test_client, mocker):
    updated = _make_storage(mount_point="/mnt/updated")
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=_make_storage(),
    )
    mock_update = mocker.patch("api.v1.external_storages.update_external_storage_in_db")
    mock_update.return_value = updated

    response = fastapi_test_client.patch(
        "/datastores/test_store",
        json={"mount_point": "/mnt/updated"},
    )
    assert response.status_code == 200
    assert response.json()["mount_point"] == "/mnt/updated"


def test_update_external_storage_not_found(fastapi_test_client, mocker):
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db", return_value=None
    )
    response = fastapi_test_client.patch(
        "/datastores/nonexistent",
        json={"mount_point": "/mnt/new"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /datastores/{storage_name}
# ---------------------------------------------------------------------------

def test_delete_external_storage_success(fastapi_test_client, mocker):
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=_make_storage(),
    )
    mocker.patch(
        "api.v1.external_storages.delete_external_storage_from_db", return_value=True
    )
    response = fastapi_test_client.delete("/datastores/test_store")
    assert response.status_code == 204


def test_delete_external_storage_not_found(fastapi_test_client, mocker):
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db", return_value=None
    )
    response = fastapi_test_client.delete("/datastores/nonexistent")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /datastores/{storage_name}/files  — register external file
# ---------------------------------------------------------------------------

def _patch_register_deps(mocker, storage, folder=True):
    """Helper: patch the three dependencies that register_external_file always calls."""
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )
    if folder is True:
        # Return a truthy MagicMock so the 404 guard passes.
        mocker.patch(
            "api.v1.external_storages.get_folder_from_db",
            return_value=mocker.MagicMock(),
        )
    else:
        mocker.patch(
            "api.v1.external_storages.get_folder_from_db",
            return_value=folder,
        )


@pytest.mark.asyncio
async def test_register_external_file_success(
    fastapi_async_test_client, mocker, tmp_path, file_response
):
    mount = tmp_path / "cases"
    mount.mkdir()
    real_file = mount / "image.dd"
    real_file.write_bytes(b"\x00" * 16)

    storage = _make_storage(mount_point=str(mount))
    _patch_register_deps(mocker, storage)
    mock_register = mocker.patch(
        "api.v1.external_storages.register_external_file_in_db"
    )
    mock_register.return_value = file_response

    response = await fastapi_async_test_client.post(
        "/datastores/test_store/files",
        json={"folder_id": 1, "relative_path": "image.dd"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_register_external_file_path_traversal(
    fastapi_async_test_client, mocker, tmp_path
):
    mount = tmp_path / "cases"
    mount.mkdir()
    storage = _make_storage(mount_point=str(mount))
    _patch_register_deps(mocker, storage)

    response = await fastapi_async_test_client.post(
        "/datastores/test_store/files",
        json={"folder_id": 1, "relative_path": "../../etc/passwd"},
    )
    assert response.status_code == 400
    assert "traversal" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_external_file_path_not_found(
    fastapi_async_test_client, mocker, tmp_path
):
    mount = tmp_path / "cases"
    mount.mkdir()
    storage = _make_storage(mount_point=str(mount))
    _patch_register_deps(mocker, storage)

    response = await fastapi_async_test_client.post(
        "/datastores/test_store/files",
        json={"folder_id": 1, "relative_path": "nonexistent.dd"},
    )
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_external_file_path_is_directory(
    fastapi_async_test_client, mocker, tmp_path
):
    mount = tmp_path / "cases"
    mount.mkdir()
    subdir = mount / "subdir"
    subdir.mkdir()
    storage = _make_storage(mount_point=str(mount))
    _patch_register_deps(mocker, storage)

    response = await fastapi_async_test_client.post(
        "/datastores/test_store/files",
        json={"folder_id": 1, "relative_path": "subdir"},
    )
    assert response.status_code == 400
    assert "not a regular file" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_external_file_storage_not_found(
    fastapi_async_test_client, mocker
):
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db", return_value=None
    )
    response = await fastapi_async_test_client.post(
        "/datastores/nonexistent/files",
        json={"folder_id": 1, "relative_path": "image.dd"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /datastores/{storage_name}/browse
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_browse_root(fastapi_async_test_client, mocker, tmp_path):
    mount = tmp_path / "cases"
    mount.mkdir()
    (mount / "image.dd").write_bytes(b"\x00" * 512)
    (mount / "logs").mkdir()
    storage = _make_storage(mount_point=str(mount))

    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )

    response = await fastapi_async_test_client.get("/datastores/test_store/browse")
    assert response.status_code == 200
    data = response.json()
    assert data["current_path"] == ""
    names = [i["name"] for i in data["items"]]
    # directories come first
    assert data["items"][0]["type"] == "directory"
    assert data["items"][0]["name"] == "logs"
    assert data["items"][1]["type"] == "file"
    assert data["items"][1]["name"] == "image.dd"
    assert data["items"][1]["size"] == 512


@pytest.mark.asyncio
async def test_browse_subdir(fastapi_async_test_client, mocker, tmp_path):
    mount = tmp_path / "cases"
    mount.mkdir()
    subdir = mount / "evidence"
    subdir.mkdir()
    (subdir / "file_a.txt").write_bytes(b"a")
    (subdir / "file_b.txt").write_bytes(b"bb")
    storage = _make_storage(mount_point=str(mount))

    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )

    response = await fastapi_async_test_client.get(
        "/datastores/test_store/browse", params={"path": "evidence"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["current_path"] == "evidence"
    assert len(data["items"]) == 2
    assert data["items"][0]["name"] == "file_a.txt"
    assert data["items"][1]["name"] == "file_b.txt"


@pytest.mark.asyncio
async def test_browse_alphabetical_sort(fastapi_async_test_client, mocker, tmp_path):
    mount = tmp_path / "cases"
    mount.mkdir()
    for name in ["zeta.bin", "alpha.bin", "mu.bin"]:
        (mount / name).write_bytes(b"x")
    for name in ["zoo", "ant", "middle"]:
        (mount / name).mkdir()
    storage = _make_storage(mount_point=str(mount))

    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )

    response = await fastapi_async_test_client.get("/datastores/test_store/browse")
    assert response.status_code == 200
    items = response.json()["items"]
    dirs = [i for i in items if i["type"] == "directory"]
    files = [i for i in items if i["type"] == "file"]
    # All dirs before all files
    assert items.index(dirs[-1]) < items.index(files[0])
    # Each group sorted alphabetically
    assert [d["name"] for d in dirs] == sorted(d["name"] for d in dirs)
    assert [f["name"] for f in files] == sorted(f["name"] for f in files)


@pytest.mark.asyncio
async def test_browse_storage_not_found(fastapi_async_test_client, mocker):
    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db", return_value=None
    )
    response = await fastapi_async_test_client.get("/datastores/nonexistent/browse")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_browse_path_traversal(fastapi_async_test_client, mocker, tmp_path):
    mount = tmp_path / "cases"
    mount.mkdir()
    storage = _make_storage(mount_point=str(mount))

    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )

    response = await fastapi_async_test_client.get(
        "/datastores/test_store/browse", params={"path": "../../etc"}
    )
    assert response.status_code == 400
    assert "traversal" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_browse_path_escapes_mount(fastapi_async_test_client, mocker, tmp_path):
    mount = tmp_path / "cases"
    mount.mkdir()
    outside = tmp_path / "secret"
    outside.mkdir()
    # Create a symlink inside mount that points outside
    symlink = mount / "escape"
    symlink.symlink_to(outside)
    storage = _make_storage(mount_point=str(mount))

    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )

    response = await fastapi_async_test_client.get(
        "/datastores/test_store/browse", params={"path": "escape"}
    )
    assert response.status_code == 400
    assert "escapes" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_browse_path_not_found(fastapi_async_test_client, mocker, tmp_path):
    mount = tmp_path / "cases"
    mount.mkdir()
    storage = _make_storage(mount_point=str(mount))

    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )

    response = await fastapi_async_test_client.get(
        "/datastores/test_store/browse", params={"path": "nonexistent"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_browse_path_is_file(fastapi_async_test_client, mocker, tmp_path):
    mount = tmp_path / "cases"
    mount.mkdir()
    (mount / "image.dd").write_bytes(b"\x00")
    storage = _make_storage(mount_point=str(mount))

    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )

    response = await fastapi_async_test_client.get(
        "/datastores/test_store/browse", params={"path": "image.dd"}
    )
    assert response.status_code == 400
    assert "not a directory" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_browse_skips_symlink_files(fastapi_async_test_client, mocker, tmp_path):
    """Symlink files must not appear in browse results (consistent with sync)."""
    mount = tmp_path / "cases"
    mount.mkdir()
    real_file = mount / "real.dd"
    real_file.write_bytes(b"\x00" * 8)
    link_file = mount / "link.dd"
    link_file.symlink_to(real_file)
    storage = _make_storage(mount_point=str(mount))

    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )

    response = await fastapi_async_test_client.get("/datastores/test_store/browse")
    assert response.status_code == 200
    names = [i["name"] for i in response.json()["items"]]
    assert "real.dd" in names
    assert "link.dd" not in names, "symlink files must be excluded from browse results"


@pytest.mark.asyncio
async def test_browse_skips_symlink_directories(fastapi_async_test_client, mocker, tmp_path):
    """Symlink directories must not appear in browse results."""
    mount = tmp_path / "cases"
    mount.mkdir()
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "secret.bin").write_bytes(b"x")
    link_dir = mount / "linked_dir"
    link_dir.symlink_to(real_dir)
    storage = _make_storage(mount_point=str(mount))

    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )

    response = await fastapi_async_test_client.get("/datastores/test_store/browse")
    assert response.status_code == 200
    names = [i["name"] for i in response.json()["items"]]
    assert "linked_dir" not in names, "symlink directories must be excluded from browse results"


# ---------------------------------------------------------------------------
# POST /datastores/{storage_name}/files  — folder authorization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_external_file_folder_not_found(
    fastapi_async_test_client, mocker, tmp_path
):
    """Returns 404 when the target folder does not exist."""
    mount = tmp_path / "cases"
    mount.mkdir()
    storage = _make_storage(mount_point=str(mount))
    _patch_register_deps(mocker, storage, folder=None)

    response = await fastapi_async_test_client.post(
        "/datastores/test_store/files",
        json={"folder_id": 999, "relative_path": "image.dd"},
    )
    assert response.status_code == 404
    assert "folder" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_external_file_calls_access_check(
    fastapi_async_test_client, mocker, tmp_path, authz, file_response
):
    """check_user_access is called with EDITOR/OWNER roles when folder exists.

    The autouse ``authz`` fixture already mocks datastores.sql.crud.authz.check_user_access
    and returns True; here we just assert it was called with the correct roles.
    """
    import uuid as uuid_module
    from datastores.sql.models.folder import Folder
    from datastores.sql.models.role import Role

    mount = tmp_path / "cases"
    mount.mkdir()
    real_file = mount / "image.dd"
    real_file.write_bytes(b"\x00" * 16)
    storage = _make_storage(mount_point=str(mount))

    mock_folder = Folder(
        id=1,
        display_name="test",
        uuid=uuid_module.uuid4(),
        user_id=1,
    )

    mocker.patch(
        "api.v1.external_storages.get_external_storage_from_db",
        return_value=storage,
    )
    mocker.patch("api.v1.external_storages.get_folder_from_db", return_value=mock_folder)
    mocker.patch(
        "api.v1.external_storages.register_external_file_in_db",
        return_value=file_response,
    )

    await fastapi_async_test_client.post(
        "/datastores/test_store/files",
        json={"folder_id": 1, "relative_path": "image.dd"},
    )

    authz.assert_called_once()
    call_args = authz.call_args
    roles_arg = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get("allowed_roles")
    assert Role.EDITOR in roles_arg
    assert Role.OWNER in roles_arg


# ---------------------------------------------------------------------------
# Issue 3 — UniqueConstraint present in File ORM model
# ---------------------------------------------------------------------------

def test_file_model_has_unique_constraint_for_external_registration():
    """The File ORM model must declare the uq_file_folder_external constraint so
    that Alembic autogenerate does not detect it as schema drift."""
    from sqlalchemy import UniqueConstraint
    from datastores.sql.models.file import File

    constraint_names = {
        c.name
        for c in File.__table_args__
        if isinstance(c, UniqueConstraint)
    }
    assert "uq_file_folder_external" in constraint_names, (
        "File model is missing __table_args__ UniqueConstraint 'uq_file_folder_external'. "
        "Add it to keep the ORM in sync with the migration."
    )
