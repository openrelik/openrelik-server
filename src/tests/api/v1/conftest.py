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

import os
from unittest.mock import PropertyMock

import pytest


@pytest.fixture
def setup_config_mock(mocker, tmp_path):
    """
    Mocks the global configuration to include the new storage provider structure,
    using tmp_path for the artifact location.

    This mock configuration satisfies the new path logic in FileDBModel and FolderDBModel.
    """
    # Use tmp_path for the mocked storage location
    temp_storage_path = str(tmp_path / "mocked_artifacts")

    mock_config_return = {
        "server": {
            "storage": {
                "providers": {
                    "default": {"path": temp_storage_path},
                    "custom": {"path": "/custom/storage/path"},
                }
            }
        }
    }
    # Mock the function that retrieves the global configuration
    # Note: Assumes the config is retrieved via datastores.sql.models.folder.get_config
    mock_config_getter = mocker.patch("datastores.sql.models.folder.get_config")
    mock_config_getter.return_value = mock_config_return

    # Ensure the directory exists so the tests can open/write files
    os.makedirs(temp_storage_path, exist_ok=True)

    return mock_config_return


@pytest.fixture
def setup_file_path_mock(mocker, file_db_model, setup_config_mock):
    """
    Sets up the necessary mocks for FileDBModel.path property to work with the new
    storage provider configuration (via setup_config_mock).

    Returns:
        str: The expected path of the mocked file.
    """
    mock_config = setup_config_mock

    # 2. Configure the file_db_model fixture attributes
    # These are needed by the path property
    file_db_model.storage_provider = "default"
    # Use the file's ID for a deterministic and unique storage key for mocking
    file_db_model.storage_key = f"file_content_{file_db_model.id}.txt"

    # Define the expected full path based on the mock config
    expected_path = os.path.join(
        mock_config["server"]["storage"]["providers"]["default"]["path"],
        file_db_model.storage_key,
    )

    # 3. Mock the 'path' property on the file_db_model class to return the expected path
    mocker.patch.object(
        file_db_model.__class__, "path", new_callable=PropertyMock, return_value=expected_path
    )

    # Return the expected path for tests that need to assert on the 'open' call
    return expected_path
