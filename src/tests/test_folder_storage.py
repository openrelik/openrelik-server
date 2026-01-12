import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from datastores.sql.models.folder import Folder


@pytest.fixture
def mock_config():
    return {
        "server": {
            "storage": {
                "providers": {
                    "default": "server_default",
                    "server_default": {"path": "/data/default"},
                    "special_provider": {"path": "/data/special"},
                }
            }
        }
    }


@patch("datastores.sql.models.folder.get_config")
def test_folder_path_default_provider(mock_get_config, mock_config):
    mock_get_config.return_value = mock_config

    folder_uuid = uuid4()
    folder = Folder(uuid=folder_uuid)  # No storage_provider set

    expected_path = os.path.join("/data/default", folder_uuid.hex)
    assert folder.path == expected_path


@patch("datastores.sql.models.folder.get_config")
def test_folder_path_special_provider(mock_get_config, mock_config):
    mock_get_config.return_value = mock_config

    folder_uuid = uuid4()
    folder = Folder(uuid=folder_uuid, storage_provider="special_provider")

    expected_path = os.path.join("/data/special", folder_uuid.hex)
    assert folder.path == expected_path


@patch("datastores.sql.models.folder.get_config")
def test_folder_path_subfolder_with_provider(mock_get_config, mock_config):
    mock_get_config.return_value = mock_config

    # Root folder with default storage
    root_uuid = uuid4()
    root_folder = Folder(uuid=root_uuid)

    # Subfolder with special storage provider (acting as mount point)
    sub_uuid = uuid4()
    sub_folder = Folder(uuid=sub_uuid, parent=root_folder, storage_provider="special_provider")

    # Expected path is directly under the special provider path, flattened by UUID
    expected_sub_path = os.path.join("/data/special", sub_uuid.hex)
    assert sub_folder.path == expected_sub_path


@patch("datastores.sql.models.folder.get_config")
def test_folder_path_nested_inheritance_from_subfolder(mock_get_config, mock_config):
    mock_get_config.return_value = mock_config

    # Root folder (default)
    root_uuid = uuid4()
    root_folder = Folder(uuid=root_uuid)

    # Subfolder 1 (special provider)
    sub1_uuid = uuid4()
    sub1_folder = Folder(uuid=sub1_uuid, parent=root_folder, storage_provider="special_provider")

    # Subfolder 2 (child of Subfolder 1) - should inherit from Subfolder 1
    sub2_uuid = uuid4()
    sub2_folder = Folder(uuid=sub2_uuid, parent=sub1_folder)

    # Logic: Subfolder 1 path + Subfolder 2 UUID
    sub1_path = os.path.join("/data/special", sub1_uuid.hex)
    expected_sub2_path = os.path.join(sub1_path, sub2_uuid.hex)

    assert sub2_folder.path == expected_sub2_path


@patch("datastores.sql.models.folder.get_config")
def test_folder_path_subfolder_inheritance(mock_get_config, mock_config):
    mock_get_config.return_value = mock_config

    root_uuid = uuid4()
    root_folder = Folder(uuid=root_uuid, storage_provider="special_provider")

    sub_uuid = uuid4()
    # Parent set on subfolder
    sub_folder = Folder(uuid=sub_uuid, parent=root_folder)

    root_path = os.path.join("/data/special", root_uuid.hex)
    expected_sub_path = os.path.join(root_path, sub_uuid.hex)

    assert sub_folder.path == expected_sub_path


def test_get_effective_storage_provider_explicit():
    folder = Folder(storage_provider="test_provider")
    assert folder.get_effective_storage_provider() == "test_provider"


def test_get_effective_storage_provider_inherited():
    root = Folder(storage_provider="test_provider")
    child = Folder(parent=root)
    assert child.get_effective_storage_provider() == "test_provider"


def test_get_effective_storage_provider_default():
    root = Folder()
    assert root.get_effective_storage_provider() is None


@patch("datastores.sql.models.folder.get_config")
def test_folder_path_fallback_old_config(mock_get_config):
    # Config without providers, just storage_path
    old_config = {"server": {"storage_path": "/data/old_default"}}
    mock_get_config.return_value = old_config

    folder_uuid = uuid4()
    folder = Folder(uuid=folder_uuid)

    expected_path = os.path.join("/data/old_default", folder_uuid.hex)
    assert folder.path == expected_path
