import json
import logging
import os
import uuid

from google.cloud import pubsub_v1, storage

from api.v1 import schemas
from datastores.sql import database
from datastores.sql.crud.file import create_file_in_db
from datastores.sql.crud.folder import get_folder_from_db
from datastores.sql.crud.user import get_user_from_db
from datastores.sql.models import file, folder, user  # noqa: F401
from lib.file_hashes import generate_hashes

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
SUBSCRIPTION_ID = os.environ.get("GOOGLE_CLOUD_SUBSCRIPTION_ID")


# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_file_from_gcs(
    storage_client: storage.Client, bucket_name: str, object_name: str, output_path: str
) -> None:
    """Downloads a file from Google Cloud Storage."""
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.download_to_filename(output_path)
        logger.info(f"Downloaded gs://{bucket_name}/{object_name} to {output_path}")
    except Exception as e:
        logger.exception(f"Error downloading file: {e}")
        raise


def extract_file_info(object_name: str) -> tuple[int, str, str, str]:
    """Extracts folder_id, filename, extension, and a UUID from the object name.

    Args:
        object_name (str): The name of the object in GCS, which includes folder_id
        and filename.

    Returns:
        tuple[int, str, str, str]: A tuple containing folder_id (int), filename (str),
        file_extension (str), and output_filename (str).

    Raises:
        Exception: If there is an error extracting the file information.
    """
    try:
        folder_id_str, filename = object_name.split("/", 1)
        folder_id = int(folder_id_str)
        _, file_extension = os.path.splitext(filename)
        file_uuid = uuid.uuid4()
        output_filename = f"{file_uuid.hex}{file_extension}"
        return folder_id, filename, file_extension, output_filename
    except Exception as e:
        logger.exception(f"Error extracting file info: {e}")
        raise


def create_file_record(
    db: object,
    filename: str,
    file_uuid: uuid.UUID,
    file_extension: str,
    folder_id: int,
    user_id: int,
) -> file.File:
    """Creates a new file record in the database."""
    try:
        new_file = schemas.FileCreate(
            display_name=filename,
            uuid=file_uuid,
            filename=filename,
            extension=file_extension.lstrip("."),
            folder_id=folder_id,
            user_id=user_id,
        )
        current_user = get_user_from_db(db, user_id)
        new_file_db = create_file_in_db(db, new_file, current_user)
        return new_file_db
    except Exception as e:
        logger.exception(f"Error creating file record: {e}")
        raise


def process_gcs_message(
    message: pubsub_v1.subscriber.message.Message,
    db: object,
) -> None:
    """Processes an incoming Pub/Sub message from GCS."""
    message.ack()
    storage_client = storage.Client(project=PROJECT_ID)
    try:
        # Decode and parse the message data
        data = message.data.decode("utf-8")
        attributes = json.loads(data)
        bucket_name = attributes["bucket"]
        object_name = attributes["name"]

        logger.info(f"Received message: bucket={bucket_name}, object={object_name}")

        if "/" not in object_name:
            logger.info(f"File is in root bucket, skipping import.")
            return  # Skip processing this file

        if object_name.endswith("/"):
            logger.info(f"GCS directory created, nothing to import.")
            return  # Skip processing this file

        # Extract file information
        folder_id, filename, file_extension, output_filename = extract_file_info(
            object_name
        )

        # TODO: How to get the user?  For now, using a placeholder
        user_id = 1

        # Get folder information
        folder = get_folder_from_db(db, folder_id)

        if not folder:
            logger.error(f"Folder with ID {folder_id} not found in OpenRelik.")
            return  # Skip processing this file

        output_path = os.path.join(folder.path, output_filename)

        # Download the file from GCS
        download_file_from_gcs(storage_client, bucket_name, object_name, output_path)

        # Create file record in the database
        new_file_db = create_file_record(
            db,
            filename,
            uuid.UUID(output_filename.split(".")[0]),
            file_extension,
            folder.id,
            user_id,
        )

        # Generate file hashes.
        # TODO: Move this to a background job (celery).
        generate_hashes(new_file_db.id)

    except Exception as e:
        logger.exception(f"Error processing message: {e}")

    finally:
        message.ack()


def main() -> None:
    """Main function to subscribe to Pub/Sub messages."""
    db = database.SessionLocal()

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

    logger.info(f"Start listening for messages on {subscription_path}...")

    # Start the listener, passing the clients to the callback
    listener = subscriber.subscribe(
        subscription_path,
        lambda message: process_gcs_message(message, db),
    )
    listener.result()


if __name__ == "__main__":
    main()
