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

import pytest
import hashlib

from lib.file_hashes import _calculate_file_hashes, generate_hashes


def test_calculate_file_hashes(mocker):
    """Test _calculate_file_hashes with mock file data."""
    file_content = b"test file content"

    # Calculate expected hashes
    md5 = hashlib.md5(file_content).hexdigest()
    sha1 = hashlib.sha1(file_content).hexdigest()
    sha256 = hashlib.sha256(file_content).hexdigest()

    m = mocker.mock_open(read_data=file_content)
    mocker.patch("builtins.open", m)

    md5_res, sha1_res, sha256_res = _calculate_file_hashes("/dummy/path")

    assert md5_res == md5
    assert sha1_res == sha1
    assert sha256_res == sha256


def test_generate_hashes(mocker, db):
    """Test generate_hashes updates the database."""
    mocker.patch("lib.file_hashes.database.SessionLocal", return_value=db)
    mock_get_file = mocker.patch("lib.file_hashes.get_file_from_db")
    mock_calc_hashes = mocker.patch("lib.file_hashes._calculate_file_hashes")

    mock_file = mocker.MagicMock()
    mock_file.path = "/dummy/path"
    mock_get_file.return_value = mock_file

    mock_calc_hashes.return_value = ("md5sum", "sha1sum", "sha256sum")

    generate_hashes(file_id=1)

    mock_get_file.assert_called_once_with(db, 1)
    mock_calc_hashes.assert_called_once_with("/dummy/path")

    assert mock_file.hash_md5 == "md5sum"
    assert mock_file.hash_sha1 == "sha1sum"
    assert mock_file.hash_sha256 == "sha256sum"

    db.commit.assert_called_once()
