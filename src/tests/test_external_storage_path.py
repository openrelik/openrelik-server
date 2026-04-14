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

"""Tests for File.path() with external storage and path traversal validation."""

import uuid

import pytest

from datastores.sql.models.external_storage import ExternalStorage
from datastores.sql.models.file import File


def _make_external_storage(mount_point: str) -> ExternalStorage:
    return ExternalStorage(
        id=1,
        name="test_store",
        mount_point=mount_point,
        description=None,
    )


def _make_file(
    external_storage_name: str = None,
    external_relative_path: str = None,
    external_storage: ExternalStorage = None,
    storage_provider: str = None,
    storage_key: str = None,
    folder=None,
    extension: str = "dd",
) -> File:
    file_uuid = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")
    return File(
        id=1,
        uuid=file_uuid,
        display_name="test.dd",
        filename="test.dd",
        filesize=1024,
        extension=extension,
        data_type="file:generic",
        user_id=1,
        folder_id=1,
        folder=folder,
        external_storage_name=external_storage_name,
        external_relative_path=external_relative_path,
        external_storage=external_storage,
        storage_provider=storage_provider,
        storage_key=storage_key,
    )


class TestExternalStoragePath:
    def test_path_returns_mount_plus_relative(self, tmp_path):
        mount = str(tmp_path / "cases")
        storage = _make_external_storage(mount)
        f = _make_file(
            external_storage_name="test_store",
            external_relative_path="case/123/image.dd",
            external_storage=storage,
        )
        expected = f"{mount}/case/123/image.dd"
        assert f.path == expected

    def test_path_strips_leading_slash_from_relative(self, tmp_path):
        mount = str(tmp_path / "cases")
        storage = _make_external_storage(mount)
        f = _make_file(
            external_storage_name="test_store",
            external_relative_path="/case/123/image.dd",
            external_storage=storage,
        )
        result = f.path
        assert not result.startswith(mount + "//")
        assert result.endswith("case/123/image.dd")

    def test_path_traversal_raises_value_error(self, tmp_path):
        mount = str(tmp_path / "cases")
        storage = _make_external_storage(mount)
        f = _make_file(
            external_storage_name="test_store",
            external_relative_path="case/../../etc/passwd",
            external_storage=storage,
        )
        with pytest.raises(ValueError, match="Path traversal"):
            _ = f.path

    def test_path_traversal_dotdot_at_start(self, tmp_path):
        mount = str(tmp_path / "cases")
        storage = _make_external_storage(mount)
        f = _make_file(
            external_storage_name="test_store",
            external_relative_path="../secret",
            external_storage=storage,
        )
        with pytest.raises(ValueError, match="Path traversal"):
            _ = f.path

    def test_path_traversal_windows_style(self, tmp_path):
        mount = str(tmp_path / "cases")
        storage = _make_external_storage(mount)
        f = _make_file(
            external_storage_name="test_store",
            external_relative_path="case\\..\\..\\secret",
            external_storage=storage,
        )
        with pytest.raises(ValueError, match="Path traversal"):
            _ = f.path

    def test_missing_external_storage_object_raises(self, tmp_path):
        f = _make_file(
            external_storage_name="missing_store",
            external_relative_path="case/image.dd",
            external_storage=None,
        )
        with pytest.raises(ValueError, match="not found in database"):
            _ = f.path

    def test_missing_relative_path_raises(self, tmp_path):
        mount = str(tmp_path / "cases")
        storage = _make_external_storage(mount)
        f = _make_file(
            external_storage_name="test_store",
            external_relative_path=None,
            external_storage=storage,
        )
        with pytest.raises(ValueError, match="No relative path"):
            _ = f.path


class TestIsExternal:
    def test_is_external_true_when_name_set(self, tmp_path):
        mount = str(tmp_path / "cases")
        storage = _make_external_storage(mount)
        f = _make_file(
            external_storage_name="test_store",
            external_relative_path="a/b.dd",
            external_storage=storage,
        )
        assert f.is_external is True

    def test_is_external_false_when_name_not_set(self):
        f = _make_file()
        assert f.is_external is False
