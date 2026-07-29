# Copyright 2025 Google LLC
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
import json
import uuid

import pytest

from importers.importer_utils import (
    create_file_record,
    extract_file_info,
    get_or_create_root_folder,
    parse_positive_int_env,
    parse_template_params,
)


def test_parse_template_params_empty_returns_empty_dict():
    assert parse_template_params("") == {}


def test_parse_template_params_valid_object():
    assert parse_template_params('{"param_1": "value"}') == {"param_1": "value"}


@pytest.mark.parametrize("bad_raw", ["not-json", "[1, 2, 3]", '"scalar"'])
def test_parse_template_params_rejects_bad_values(bad_raw):
    with pytest.raises(ValueError):
        parse_template_params(bad_raw)


def test_parse_template_params_json_error_preserves_cause():
    """ValueError must chain from JSONDecodeError for debuggability."""
    with pytest.raises(ValueError) as excinfo:
        parse_template_params("not-json")
    assert isinstance(excinfo.value.__cause__, json.JSONDecodeError)


@pytest.mark.parametrize("raw", [None, ""])
def test_parse_positive_int_env_none_or_empty_returns_none(raw):
    """Unset or empty env is the canonical "disabled" signal and must not raise."""
    assert parse_positive_int_env("MY_VAR", raw) is None


@pytest.mark.parametrize("raw,expected", [("1", 1), ("42", 42), ("99999", 99999)])
def test_parse_positive_int_env_valid(raw, expected):
    assert parse_positive_int_env("MY_VAR", raw) == expected


@pytest.mark.parametrize("raw", ["abc", "1.5", " ", "1 2", "0x1"])
def test_parse_positive_int_env_rejects_non_integers(raw):
    """Non-integer values must fail fast at startup, not per-message."""
    with pytest.raises(ValueError, match="MY_VAR"):
        parse_positive_int_env("MY_VAR", raw)


@pytest.mark.parametrize("raw", ["0", "-1", "-99"])
def test_parse_positive_int_env_rejects_non_positive(raw):
    """0 and negatives are invalid; positive-only is part of the contract."""
    with pytest.raises(ValueError, match="MY_VAR"):
        parse_positive_int_env("MY_VAR", raw)


def test_extract_file_info():
    folder_id, filename, file_extension, output_filename = extract_file_info(
        "12345/testfile.txt"
    )
    assert folder_id == 12345
    assert filename == "testfile.txt"
    assert file_extension == ".txt"
    assert isinstance(uuid.UUID(output_filename.split(".")[0]), uuid.UUID)


def test_extract_file_info_no_slash():
    with pytest.raises(ValueError) as excinfo:
        extract_file_info("testfile.txt")
    assert "does not contain a forward slash" in str(excinfo.value)


def test_extract_file_info_no_extension():
    folder_id, filename, file_extension, output_filename = extract_file_info(
        "12345/testfile"
    )
    assert folder_id == 12345
    assert filename == "testfile"
    assert file_extension == ""
    assert isinstance(uuid.UUID(output_filename.split(".")[0]), uuid.UUID)


def test_extract_file_info_nested_path():
    """Only the first segment is the folder id; the rest stays as filename."""
    folder_id, filename, file_extension, _ = extract_file_info("7/sub/dir/file.bin")
    assert folder_id == 7
    assert filename == "sub/dir/file.bin"
    assert file_extension == ".bin"


def test_extract_file_info_non_integer_folder():
    with pytest.raises(ValueError):
        extract_file_info("not-a-number/file.txt")


def test_create_file_record(mocker):
    mock_db = mocker.MagicMock()
    mock_get_user_from_db = mocker.patch("importers.importer_utils.get_user_from_db")
    mock_create_file_in_db = mocker.patch("importers.importer_utils.create_file_in_db")

    create_file_record(
        mock_db, "testfile.txt", uuid.uuid4(), ".txt", folder_id=123, user_id=1
    )

    mock_get_user_from_db.assert_called_once_with(mock_db, 1)
    mock_create_file_in_db.assert_called_once()


def test_get_or_create_root_folder_returns_existing(mocker):
    """If a matching root folder owned by the user already exists, reuse it."""
    mock_db = mocker.MagicMock()
    mock_owner = mocker.MagicMock()
    mock_owner.id = 1
    mocker.patch("importers.importer_utils.get_user_from_db", return_value=mock_owner)
    existing_folder = mocker.MagicMock(name="existing_folder")
    # .query(Folder).join(...).filter(...).first() returns the folder.
    mock_db.query.return_value.join.return_value.filter.return_value.first.return_value = (
        existing_folder
    )
    mock_create = mocker.patch("importers.importer_utils.create_root_folder_in_db")

    result = get_or_create_root_folder(mock_db, "mytestCase", user_id=1)

    assert result is existing_folder
    mock_create.assert_not_called()


def test_get_or_create_root_folder_creates_when_missing(mocker):
    """When no matching folder exists, create a new root folder for the user."""
    mock_db = mocker.MagicMock()
    mock_owner = mocker.MagicMock()
    mock_owner.id = 1
    mocker.patch("importers.importer_utils.get_user_from_db", return_value=mock_owner)
    mock_db.query.return_value.join.return_value.filter.return_value.first.return_value = (
        None
    )
    new_folder = mocker.MagicMock(name="new_folder")
    mock_create = mocker.patch(
        "importers.importer_utils.create_root_folder_in_db", return_value=new_folder
    )

    result = get_or_create_root_folder(mock_db, "mytestCase", user_id=1)

    assert result is new_folder
    mock_create.assert_called_once()
    # Second positional arg is the FolderCreateRequest; third is the owner.
    args, _ = mock_create.call_args
    assert args[0] is mock_db
    assert args[1].display_name == "mytestCase"
    assert args[2] is mock_owner
