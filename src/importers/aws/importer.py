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
"""AWS S3/SQS importer: polls SQS for object-create events and ingests files.

TODO(importer-bucket-isolation): folder mirroring uses path_parts[0] as the
root folder and ignores bucket_name, so the same key from two different
buckets collides in one folder tree. When multi-bucket deployments are in
play, prepend bucket_name as the root and walk every path_parts segment as
a subfolder. Tracked separately.

TODO(importer-dedup): SQS is at-least-once; a crash between create_file_record
and sqs.delete_message causes duplicate ingestion of the same (bucket, key,
version) on redelivery. Needs a dedup check against a source-identity attribute
on File (or a dedicated table with a unique constraint). Tracked separately.
"""

import json
import logging
import os
import time
import uuid
from typing import Any, Dict
from urllib.parse import unquote_plus

import boto3
from sqlalchemy.orm import Session

from datastores.sql import database
from datastores.sql.crud.user import get_user_from_db
from datastores.sql.crud.workflow import get_workflow_template_from_db
from datastores.sql.models.user import User
from importers.importer_utils import (
    create_file_record,
    get_or_create_root_folder,
    get_or_create_subfolder,
    parse_positive_int_env,
    parse_template_params
)
from lib import workflow_utils
from lib.file_hashes import generate_hashes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS_REGOIN, AWS_SQS_QUEUE_URL, and ROBOT_ACCOUNT_USER_ID are required.
AWS_REGION = os.environ.get("AWS_REGION")
SQS_QUEUE_URL = os.environ.get("AWS_SQS_QUEUE_URL")
ROBOT_ACCOUNT_USER_ID: int | None = parse_positive_int_env(
    "ROBOT_ACCOUNT_USER_ID", os.environ.get("ROBOT_ACCOUNT_USER_ID")
)

# AWS_IMPORT_TEMPLATE_ID is optional — leave unset to disable workflow auto-run.
AWS_IMPORT_TEMPLATE_ID: int | None = parse_positive_int_env(
    "AWS_IMPORT_TEMPLATE_ID", os.environ.get("AWS_IMPORT_TEMPLATE_ID")
)

# AWS_IMPORT_TEMPLATE_PARAMS is optional - parameteers must be a JSON object if
# set, and are passed through to the workflow template as-is.
AWS_IMPORT_TEMPLATE_PARAMS: Dict[str, Any] = parse_template_params(
    os.environ.get("AWS_IMPORT_TEMPLATE_PARAMS", "")
)

# Files above this size are not hashed.
HASH_SIZE_LIMIT = 10 * 1024 * 1024

# SQS caps MaxNumberOfMessages at 10 and WaitTimeSeconds at 20; 
# the receive-error backoff avoids busy-looping on transient errors.
SQS_MAX_MESSAGES = 10
SQS_WAIT_TIME_SECONDS = 20
RECEIVE_ERROR_BACKOFF_SECONDS = 5


def parse_key(object_key: str) -> tuple[list[str], str]:
    """Split an S3 key into (folder path segments, filename).

    The key's directory structure is mirrored into the OpenRelik folder
    tree. The key must contain at least one ``/`` — keys with no prefix
    are rejected because the importer has no folder to place them under.

    Examples:
        ``root/abc/data/file.zip`` -> ``(["root", "abc", "data"], "file.zip")``
        ``uploads/file.txt``       -> ``(["uploads"], "file.txt")``

    Args:
        object_key: The URL-decoded S3 object key.

    Returns:
        A 2-tuple of (path_parts, filename).

    Raises:
        ValueError: If the key has no ``/`` (no folder segment), any segment
            is empty, any segment is ``.`` or ``..``, or any segment contains
            a backslash or NUL byte (all of which could produce ambiguous or
            unsafe display names in the folder tree).
    """
    parts = object_key.split("/")
    if len(parts) < 2:
        raise ValueError(
            f"Key {object_key!r} has no folder prefix; expected at least "
            "one '/' separator."
        )
    *path_parts, filename = parts
    invalid_segments = set(["", ".", "..", "\\", "\x00"])
    for segment in (*path_parts, filename):
        if not segment:
            raise ValueError(f"Key {object_key!r} contains an empty path segment.")
        if segment in invalid_segments:
            raise ValueError(
                f"Key {object_key!r} contains invalid path segment {segment!r}."
            )
    return path_parts, filename


def download_file_from_s3(
    s3_client: Any, bucket_name: str, object_key: str, output_path: str
) -> None:
    """Downloads an S3 object to ``output_path`` via an atomic rename.

    Writes to ``output_path + ".partial"`` first and ``os.replace``s into
    place on success, so a crash mid-download never leaves a truncated file
    visible at ``output_path``. On any exception, the ``.partial`` file is
    removed before re-raising.

    Args:
        s3_client: A boto3 S3 client.
        bucket_name: Name of the S3 bucket.
        object_key: S3 object key.
        output_path: Local path to save the downloaded file.
    """
    partial_path = f"{output_path}.partial"
    try:
        s3_client.download_file(bucket_name, object_key, partial_path)
        os.replace(partial_path, output_path)
    except Exception:
        # boto3 may leave its own multipart .tmp shards behind on failure;
        # those aren't covered here and rely on a future reconciler.
        try:
            os.unlink(partial_path)
        except FileNotFoundError:
            pass
        except OSError:
            logger.exception("Failed to remove partial download %s", partial_path)
        raise
    logger.info("Downloaded s3://%s/%s to %s", bucket_name, object_key, output_path)


def process_s3_record(
    s3_client: Any,
    record: Dict[str, Any],
    db: Session,
    robot_user: User,
) -> None:
    """Processes a single S3 event record from an SQS message.

    Args:
        s3_client: A boto3 S3 client.
        record: The S3 event record.
        db: Database session.
        robot_user: The user under which imports and auto-run workflows are
            attributed.
    """
    try:
        s3_info = record["s3"]
        object_key = unquote_plus(s3_info["object"]["key"])
        bucket_name = s3_info["bucket"]["name"]
        object_size = int(s3_info["object"].get("size", 0))
    except (KeyError, TypeError, ValueError):
        # Return early if record is invalid to avoid redelivery.
        logger.exception("Skipping malformed S3 event record: %r", record)
        return

    logger.info("Processing S3 object: s3://%s/%s", bucket_name, object_key)

    if object_key.endswith("/"):
        logger.info("S3 directory marker, nothing to import.")
        return

    try:
        path_parts, filename = parse_key(object_key)
    except ValueError as e:
        logger.error("Skipping object with unexpected key layout: %s", e)
        return

    _, file_extension = os.path.splitext(filename)
    file_uuid = uuid.uuid4()
    output_filename = f"{file_uuid.hex}{file_extension}"

    # Mirror the S3 directory path into the robot user's folder tree.
    folder = get_or_create_root_folder(db, path_parts[0], ROBOT_ACCOUNT_USER_ID)
    for segment in path_parts[1:]:
        folder = get_or_create_subfolder(db, folder.id, segment, ROBOT_ACCOUNT_USER_ID)

    output_path = os.path.join(folder.path, output_filename)

    # Download and DB-insert failures are logged and raised to avoid message
    # deletion, which would cause silent data loss.
    try:
        download_file_from_s3(s3_client, bucket_name, object_key, output_path)
    except Exception as e:
        logger.error("Error downloading s3://%s/%s: %s", bucket_name, object_key, e)
        raise

    try:
        new_file_db = create_file_record(
            db,
            filename,
            file_uuid,
            file_extension,
            folder.id,
            ROBOT_ACCOUNT_USER_ID,
        )
    except Exception as e:
        logger.error(
            "Error recording file s3://%s/%s: %s; removing downloaded copy at %s",
            bucket_name,
            object_key,
            e,
            output_path,
        )
        try:
            os.unlink(output_path)
        except FileNotFoundError:
            pass
        except OSError:
            logger.exception("Failed to remove orphan file %s", output_path)
        raise

    if object_size < HASH_SIZE_LIMIT:
        try:
            generate_hashes(new_file_db.id)
        except Exception:
            logger.exception("Hashing failed for file %s", new_file_db.id)

    if AWS_IMPORT_TEMPLATE_ID is not None:
        # Carry the original artifact's name (sans extension) into the auto-run
        # workflow out-of-band. By the time the exporters run, the pipeline has
        # fanned the IZE out into many files and collapsed them back into
        # UUID-named plaso/psort output, so no per-file field still holds the
        # source name. The exporters substitute this into their name patterns'
        # generic {identifier} placeholder; template authors add the
        # per-task distinguisher (e.g. a slice suffix) around it, so this stays
        # correct even when a template fans out into multiple psort/export tasks.
        identifier = os.path.splitext(filename)[0]
        template_params = {
            **AWS_IMPORT_TEMPLATE_PARAMS,
            "identifier": identifier,
        }
        try:
            _run_template_workflow(
                db,
                folder_id=folder.id,
                file_id=new_file_db.id,
                display_name=f"{filename}.workflow",
                user=robot_user,
                template_params=template_params,
            )
        except Exception:
            # Currently these failures will result in the file being imported
            # but the workflow not running; Probably change this to raise and
            # redeliver in the future.
            logger.warning(
                "Processed s3://%s/%s but workflow auto-run failed",
                bucket_name,
                object_key,
                exc_info=True,
            )
            logger.info(
                "Imported s3://%s/%s (workflow auto-run failed; see prior WARNING)",
                bucket_name,
                object_key,
            )
            return

    logger.info("Successfully processed s3://%s/%s", bucket_name, object_key)


def _run_template_workflow(
    db: Session,
    *,
    folder_id: int,
    file_id: int,
    display_name: str,
    user: User,
    template_params: Dict[str, Any],
) -> None:
    """Create a workflow from the configured template and dispatch it, in-process.

    Args:
        db: Database session.
        folder_id: The openrelik folder the imported file lives in. The
            workflow will be created as a subfolder underneath.
        file_id: The id of the newly imported file to run against.
        display_name: Display name for the new workflow and its results
            subfolder.
        user: The user under which the workflow is created and run.
        template_params: Parameter values applied to the template's task
            configs by ``param_name`` (the static ``AWS_IMPORT_TEMPLATE_PARAMS``
            merged with per-import values such as ``identifier``).
    """
    workflow = workflow_utils.create_workflow(
        db,
        folder_id=folder_id,
        file_ids=[file_id],
        template_id=AWS_IMPORT_TEMPLATE_ID,
        template_params=template_params,
        user=user,
        display_name=display_name,
    )

    workflow_utils.run_workflow(
        db,
        workflow=workflow,
        workflow_spec=json.loads(workflow.spec_json),
        user=user,
    )
    logger.info(
        "Started workflow %s from template %s for file %s",
        workflow.id,
        AWS_IMPORT_TEMPLATE_ID,
        file_id,
    )


def _extract_s3_records(message: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Extracts S3 event records from an SQS message body.

    SQS can deliver S3 events directly or wrapped inside an SNS notification.
    This handles both shapes and returns only records for object-create events.

    Args:
        message: An SQS message dict.

    Returns:
        A list of S3 event records for ObjectCreated events.
    """
    try:
        body = json.loads(message.get("Body") or "")
        # SNS-wrapped notifications put the S3 payload inside the "Message" field.
        if isinstance(body, dict) and "Message" in body and "Records" not in body:
            body = json.loads(body["Message"])
    except (TypeError, json.JSONDecodeError):
        logger.exception("SQS message body is not valid JSON; dropping.")
        return []

    records = body.get("Records") if isinstance(body, dict) else None
    if not records:
        return []

    return [
        r for r in records if str(r.get("eventName", "")).startswith("ObjectCreated:")
    ]


def process_sqs_message(s3_client: Any, message: Dict[str, Any]) -> None:
    """Processes a single SQS message, which may contain multiple S3 records.

    Each record gets its own database session and its own robot-user lookup,
    so a failure on one record doesn't poison the rest of the batch (SQS can
    deliver up to ~10 S3 notifications per message). The ORM user instance
    also stays attached to the session doing the writes.

    Args:
        s3_client: A boto3 S3 client.
        message: The SQS message dict.
    """
    records = _extract_s3_records(message)
    if not records:
        logger.info("SQS message contains no ObjectCreated records, skipping.")
        return

    for record in records:
        with database.SessionLocal() as db:
            robot_user = get_user_from_db(db, ROBOT_ACCOUNT_USER_ID)
            process_s3_record(s3_client, record, db, robot_user)


def _validate_startup_config() -> bool:
    """Pre-flight check that configured ids resolve in the DB.

    Returns:
        True if startup config is valid, False if a misconfiguration was
        detected and logged. Caller should bail on False.
    """
    if ROBOT_ACCOUNT_USER_ID is None:
        logger.error("ROBOT_ACCOUNT_USER_ID environment variable is not set.")
        return False
    if not SQS_QUEUE_URL:
        logger.error("AWS_SQS_QUEUE_URL environment variable is not set.")
        return False

    with database.SessionLocal() as db:
        if get_user_from_db(db, ROBOT_ACCOUNT_USER_ID) is None:
            logger.error(
                "ROBOT_ACCOUNT_USER_ID=%r does not match any user in the database.",
                ROBOT_ACCOUNT_USER_ID,
            )
            return False
        if (
            AWS_IMPORT_TEMPLATE_ID is not None
            and get_workflow_template_from_db(db, AWS_IMPORT_TEMPLATE_ID) is None
        ):
            logger.error(
                "AWS_IMPORT_TEMPLATE_ID=%r does not match any workflow template "
                "in the database.",
                AWS_IMPORT_TEMPLATE_ID,
            )
            return False
    return True


def main() -> None:
    """Poll the configured SQS queue and process incoming S3 events.

    Messages are only deleted from the queue after successful processing so
    that transient failures result in redelivery (subject to the queue's
    redrive policy).
    """

    if not _validate_startup_config():
        return

    sqs = boto3.client("sqs", region_name=AWS_REGION)
    s3 = boto3.client("s3", region_name=AWS_REGION)

    template_note = (
        f" Workflow auto-run enabled (template_id={AWS_IMPORT_TEMPLATE_ID})."
        if AWS_IMPORT_TEMPLATE_ID is not None
        else " Workflow auto-run disabled."
    )
    logger.info(f"Starting to poll SQS queue {SQS_QUEUE_URL}.{template_note}")

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=SQS_MAX_MESSAGES,
                WaitTimeSeconds=SQS_WAIT_TIME_SECONDS,
            )
        except Exception:  # boto3 exceptions vary; back off and retry.
            logger.exception(
                "Error receiving SQS messages, backing off for %d seconds",
                RECEIVE_ERROR_BACKOFF_SECONDS,
            )
            time.sleep(RECEIVE_ERROR_BACKOFF_SECONDS)
            continue

        messages = response.get("Messages", [])
        if not messages:
            continue

        for message in messages:
            receipt_handle = message.get("ReceiptHandle")
            try:
                process_sqs_message(s3, message)
            except Exception:
                logger.exception("Error processing SQS message")
                # Don't delete — let the queue redeliver after visibility timeout.
                continue

            try:
                sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
            except Exception:
                # Delete failure means the message will be redelivered; the
                # per-record dedup TODO above is the guard against duplicate
                # ingestion.
                logger.exception("Error deleting SQS message")


if __name__ == "__main__":
    main()
