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

import sys
import uuid
import pytest


@pytest.fixture
def importer_lib(mocker):
    mock_pubsub = mocker.MagicMock()
    mock_storage = mocker.MagicMock()

    mocker.patch.dict(
        "sys.modules",
        {
            "google.cloud.pubsub_v1": mock_pubsub,
            "google.cloud.storage": mock_storage,
        },
    )

    try:
        import google.cloud

        google.cloud.pubsub_v1 = mock_pubsub
        google.cloud.storage = mock_storage
    except ImportError:
        mock_google = mocker.MagicMock()
        mock_google.pubsub_v1 = mock_pubsub
        mock_google.storage = mock_storage
        mocker.patch.dict("sys.modules", {"google.cloud": mock_google})

    from importers.gcp.importer import download_file_from_gcs, process_gcs_message, main

    return download_file_from_gcs, process_gcs_message, main


def test_download_file_from_gcs(importer_lib, mocker):
    download_file_from_gcs, _, _ = importer_lib
    mock_storage_client = mocker.MagicMock()
    mock_bucket = mock_storage_client.bucket.return_value
    mock_blob = mock_bucket.blob.return_value

    download_file_from_gcs(
        mock_storage_client, "my-bucket", "my-object", "/path/to/output"
    )

    mock_storage_client.bucket.assert_called_once_with("my-bucket")
    mock_bucket.blob.assert_called_once_with("my-object")
    mock_blob.download_to_filename.assert_called_once_with("/path/to/output")


def test_process_gcs_message_success(importer_lib, mocker):
    _, process_gcs_message, _ = importer_lib
    mock_extract_file_info = mocker.patch("importers.gcp.importer.extract_file_info")
    mock_get_folder = mocker.patch("importers.gcp.importer.get_folder_from_db")
    mock_storage_client = mocker.patch("importers.gcp.importer.storage.Client")
    mock_create_file_record = mocker.patch("importers.gcp.importer.create_file_record")
    mock_generate_hashes = mocker.patch("importers.gcp.importer.generate_hashes")

    mock_message = mocker.MagicMock()
    mock_message.data = (
        b'{"bucket": "my-bucket", "name": "folder/file.txt", "size": "100"}'
    )

    mock_db = mocker.MagicMock()

    valid_uuid_str = "12345678-1234-5678-1234-567812345678"
    mock_extract_file_info.return_value = (
        1,
        "file.txt",
        ".txt",
        f"{valid_uuid_str}.txt",
    )
    mock_folder = mocker.MagicMock()
    mock_folder.path = "/folder/path"
    mock_folder.id = 1
    mock_get_folder.return_value = mock_folder

    mock_client_instance = mock_storage_client.return_value
    mock_bucket = mock_client_instance.bucket.return_value
    mock_blob = mock_bucket.blob.return_value

    mock_file_db = mocker.MagicMock()
    mock_file_db.id = 123
    mock_create_file_record.return_value = mock_file_db

    process_gcs_message(mock_message, mock_db)

    mock_message.ack.assert_called_once()
    mock_extract_file_info.assert_called_once_with("folder/file.txt")
    mock_get_folder.assert_called_once_with(mock_db, 1)
    mock_storage_client.assert_called_once()
    mock_create_file_record.assert_called_once()
    mock_generate_hashes.assert_called_once_with(123)


def test_process_gcs_message_root_file(importer_lib, mocker):
    _, process_gcs_message, _ = importer_lib
    mock_message = mocker.MagicMock()
    mock_message.data = b'{"bucket": "my-bucket", "name": "file.txt", "size": "100"}'
    mock_db = mocker.MagicMock()

    process_gcs_message(mock_message, mock_db)

    mock_message.ack.assert_called_once()


def test_process_gcs_message_directory(importer_lib, mocker):
    _, process_gcs_message, _ = importer_lib
    mock_message = mocker.MagicMock()
    mock_message.data = b'{"bucket": "my-bucket", "name": "folder/", "size": "0"}'
    mock_db = mocker.MagicMock()

    process_gcs_message(mock_message, mock_db)

    mock_message.ack.assert_called_once()


def test_process_gcs_message_folder_not_found(importer_lib, mocker):
    _, process_gcs_message, _ = importer_lib
    mock_extract_file_info = mocker.patch("importers.gcp.importer.extract_file_info")
    mock_get_folder = mocker.patch("importers.gcp.importer.get_folder_from_db")

    mock_message = mocker.MagicMock()
    mock_message.data = (
        b'{"bucket": "my-bucket", "name": "folder/file.txt", "size": "100"}'
    )
    mock_db = mocker.MagicMock()

    mock_extract_file_info.return_value = (1, "file.txt", ".txt", "uuid.txt")
    mock_get_folder.return_value = None

    process_gcs_message(mock_message, mock_db)

    mock_message.ack.assert_called_once()
    mock_get_folder.assert_called_once_with(mock_db, 1)


def test_process_gcs_message_extract_error(importer_lib, mocker):
    _, process_gcs_message, _ = importer_lib
    mock_extract_file_info = mocker.patch("importers.gcp.importer.extract_file_info")

    mock_message = mocker.MagicMock()
    mock_message.data = (
        b'{"bucket": "my-bucket", "name": "folder/file.txt", "size": "100"}'
    )
    mock_db = mocker.MagicMock()

    mock_extract_file_info.side_effect = ValueError("Invalid name")

    process_gcs_message(mock_message, mock_db)

    mock_message.ack.assert_called_once()


def test_process_gcs_message_download_error(importer_lib, mocker):
    _, process_gcs_message, _ = importer_lib
    mock_extract_file_info = mocker.patch("importers.gcp.importer.extract_file_info")
    mock_get_folder = mocker.patch("importers.gcp.importer.get_folder_from_db")
    mock_download = mocker.patch("importers.gcp.importer.download_file_from_gcs")

    mock_message = mocker.MagicMock()
    mock_message.data = (
        b'{"bucket": "my-bucket", "name": "folder/file.txt", "size": "100"}'
    )
    mock_db = mocker.MagicMock()

    mock_extract_file_info.return_value = (1, "file.txt", ".txt", "uuid.txt")
    mock_folder = mocker.MagicMock()
    mock_folder.path = "/folder/path"
    mock_get_folder.return_value = mock_folder

    mock_download.side_effect = Exception("Download failed")

    process_gcs_message(mock_message, mock_db)

    mock_message.ack.assert_called_once()


def test_main_no_robot_user(importer_lib, mocker):
    _, _, main = importer_lib
    mocker.patch("importers.gcp.importer.ROBOT_ACCOUNT_USER_ID", None)
    main()


def test_main_success(importer_lib, mocker):
    _, _, main = importer_lib
    mock_subscriber_client = mocker.patch(
        "importers.gcp.importer.pubsub_v1.SubscriberClient"
    )
    mocker.patch("importers.gcp.importer.ROBOT_ACCOUNT_USER_ID", "1")

    mock_subscriber = mock_subscriber_client.return_value
    mock_subscriber.subscription_path.return_value = "sub_path"
    mock_listener = mock_subscriber.subscribe.return_value

    main()

    mock_subscriber.subscribe.assert_called_once()
    mock_listener.result.assert_called_once()


def test_main_exception(importer_lib, mocker):
    _, _, main = importer_lib
    mock_subscriber_client = mocker.patch(
        "importers.gcp.importer.pubsub_v1.SubscriberClient"
    )
    mocker.patch("importers.gcp.importer.ROBOT_ACCOUNT_USER_ID", "1")

    mock_subscriber = mock_subscriber_client.return_value
    mock_subscriber.subscription_path.side_effect = Exception("error")

    main()
