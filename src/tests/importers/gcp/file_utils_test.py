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
import uuid

import pytest

from importers.gcp.file_utils import extract_file_info, create_file_record


def test_extract_file_info():
    object_name = "12345/testfile.txt"
    folder_id, filename, file_extension, output_filename = extract_file_info(object_name)

    assert folder_id == 12345
    assert filename == "testfile.txt"
    assert file_extension == ".txt"
    assert isinstance(uuid.UUID(output_filename.split(".")[0]), uuid.UUID)


def test_extract_file_info_no_slash():
    with pytest.raises(ValueError) as excinfo:
        extract_file_info("testfile.txt")
    assert "Object name 'testfile.txt' does not contain a forward slash." in str(excinfo.value)


def test_extract_file_info_no_extension():
    object_name = "12345/testfile"
    folder_id, filename, file_extension, output_filename = extract_file_info(object_name)

    assert folder_id == 12345
    assert filename == "testfile"
    assert file_extension == ""
    assert isinstance(uuid.UUID(output_filename.split(".")[0]), uuid.UUID)


def test_create_file_record(mocker):
    """Test create_file_record function with mocked database interactions."""
    mock_db = mocker.MagicMock()
    mock_get_user_from_db = mocker.patch("importers.gcp.file_utils.get_user_from_db")
    mock_create_file_in_db = mocker.patch("importers.gcp.file_utils.create_file_in_db")

    filename = "testfile.txt"
    file_uuid = uuid.uuid4()
    file_extension = ".txt"
    folder_id = 123
    user_id = 1

    create_file_record(mock_db, filename, file_uuid, file_extension, folder_id, user_id)

    mock_get_user_from_db.assert_called_once_with(mock_db, user_id)
    mock_create_file_in_db.assert_called_once()
