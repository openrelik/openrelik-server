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

import hashlib
from pathlib import Path

import pytest

from lib.file_hashes import _calculate_file_hashes


# A pytest fixture that provides a temporary directory for the test.
@pytest.fixture
def temp_file(tmp_path: Path):
    """
    Creates a temporary file for testing and returns its path.
    """
    file_content = b"This is a test file for calculating hashes."
    file_path = tmp_path / "test_file.txt"
    file_path.write_bytes(file_content)
    return file_path, file_content


def test_calculate_file_hashes(temp_file):
    """
    Tests the _calculate_file_hashes function using a temporary file.
    """
    file_path, file_content = temp_file

    # Calculate the expected hashes for the file content
    expected_md5 = hashlib.md5(file_content).hexdigest()
    expected_sha1 = hashlib.sha1(file_content).hexdigest()
    expected_sha256 = hashlib.sha256(file_content).hexdigest()

    # Call the function with the path to the temporary file
    calculated_md5, calculated_sha1, calculated_sha256 = _calculate_file_hashes(file_path)

    # Assert that the calculated hashes match the expected hashes
    assert calculated_md5 == expected_md5
    assert calculated_sha1 == expected_sha1
    assert calculated_sha256 == expected_sha256
