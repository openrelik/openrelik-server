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
import logging
import os
import uuid

from google.cloud import pubsub_v1, storage

from datastores.sql import database
from datastores.sql.crud.folder import get_folder_from_db
from importers.gcp.file_utils import create_file_record, extract_file_info
from lib.file_hashes import generate_hashes

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
SUBSCRIPTION_ID = os.environ.get("GOOGLE_CLOUD_SUBSCRIPTION_ID")
ROBOT_ACCOUNT_USER_ID = os.environ.get("ROBOT_ACCOUNT_USER_ID")
HASH_SIZE_LIMIT = 10485760  # 10MB

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_file_from_gcs(
    storage_client: storage.Client, bucket_name: str, object_name: str, output_path: str
) -> None:
    """Downloads a file from Google Cloud Storage.

    Args:
        storage_client: Google Cloud Storage client.
        bucket_name: Name of the GCS bucket.
        object_name: Name of the object (file) in the bucket.
        output_path: Local path to save the downloaded file.

    Raises:
        Exception: If any error occurs during the download process.
    """
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.download_to_filename(output_path)
    logger.info(f"Downloaded gs://{bucket_name}/{object_name} to {output_path}")


def process_gcs_message(
    message: pubsub_v1.subscriber.message.Message,
    db: object,
) -> None:
    """Processes an incoming Pub/Sub message from GCS.

    This function handles the processing of a Google Cloud Storage (GCS)
    object creation event received via Pub/Sub. It extracts file metadata,
    downloads the file, creates a file record in the database, and
    generates file hashes.

    Args:
        message: The Pub/Sub message containing GCS event data.
        db: The database session.

    Raises:
        Exception: If any error occurs during the processing.
    """
    # Acknowledge the message immediately to prevent reprocessing
    message.ack()

    # Extract GCS data from the Pub/Sub message
    data = json.loads(message.data.decode("utf-8"))
    bucket_name = data["bucket"]
    object_name = data["name"]
    object_size = int(data["size"])

    logger.info(f"Processing GCS file: gs://{bucket_name}/{object_name}")

    # Skip processing if the file is in the root bucket or is a directory
    if "/" not in object_name:
        logger.info("File is in root bucket, skipping import.")
        return

    if object_name.endswith("/"):
        logger.info("GCS directory created, nothing to import.")
        return

    # Extract file metadata
    try:
        folder_id, filename, file_extension, output_filename = extract_file_info(
            object_name
        )
    except ValueError as e:
        logger.error(f"Error extracting file metadata: {e}")
        return

    # Get folder information from the database
    folder = get_folder_from_db(db, folder_id)
    if not folder:
        logger.error(f"Folder with ID {folder_id} not found in OpenRelik.")
        return

    # Construct the output path
    output_path = os.path.join(folder.path, output_filename)

    # Download the file from GCS
    storage_client = storage.Client(project=PROJECT_ID)
    try:
        download_file_from_gcs(storage_client, bucket_name, object_name, output_path)
    except Exception as e:  # We don't know what exceptions the GCS client might raise.
        logger.error(f"Error downloading file from GCS: {e}")
        return

    # Create file record in the database
    new_file_db = create_file_record(
        db,
        filename,
        uuid.UUID(output_filename.split(".")[0]),
        file_extension,
        folder.id,
        ROBOT_ACCOUNT_USER_ID,
    )

    # Generate file hashes (consider moving this to a background job)
    # Only calculate hashes for files less than 10MB.
    if object_size < HASH_SIZE_LIMIT:
        generate_hashes(new_file_db.id)

    logger.info(f"Successfully processed gs://{bucket_name}/{object_name}")


def main() -> None:
    """
    Main function to subscribe to Pub/Sub messages and process GCS events.

    This function initializes a database session, creates a Pub/Sub subscriber client,
    subscribes to the specified subscription path, and listens for incoming messages.
    Each message is then processed by the process_gcs_message function.
    """
    if not ROBOT_ACCOUNT_USER_ID:
        logger.error("ROBOT_ACCOUNT_USER_ID environment variable is not set.")
        return
    try:
        # Initialize database session
        db = database.SessionLocal()

        # Create a Pub/Sub subscriber client
        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

        logger.info(f"Starting to listen for messages on {subscription_path}...")

        # Define a callback function to process incoming messages
        def callback(message: pubsub_v1.subscriber.message.Message) -> None:
            process_gcs_message(message, db)

        # Subscribe to the subscription path and start listening for messages
        listener = subscriber.subscribe(subscription_path, callback=callback)
        # The result() call will block until the listener is done.
        listener.result()

    except Exception as e:  # Broad exception handling to catch all errors in main.
        logger.exception(f"An error occurred during processing: {e}")

    finally:
        # Clean up resources by closing the database session
        if db:
            db.close()


if __name__ == "__main__":
    main()
