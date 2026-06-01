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

import json

import pytest


@pytest.fixture
def importer_lib(mocker):
    """Import the aws importer with boto3 stubbed.

    boto3 isn't installed in the server's dev venv, so stub it at
    ``sys.modules`` level before importing the module under test.
    """
    mocker.patch.dict("sys.modules", {"boto3": mocker.MagicMock()})

    from importers.aws.importer import (
        download_file_from_s3,
        main,
        parse_key,
        process_s3_record,
        process_sqs_message,
    )

    return {
        "download_file_from_s3": download_file_from_s3,
        "main": main,
        "parse_key": parse_key,
        "process_s3_record": process_s3_record,
        "process_sqs_message": process_sqs_message,
    }


def _make_robot_user(mocker, user_id=42):
    user = mocker.MagicMock()
    user.id = user_id
    return user


def _make_s3_record(
    bucket="fcicollectors",
    key="test/mytestCase/folder/filename.zip",
    size=100,
    event_name="ObjectCreated:Put",
):
    return {
        "eventName": event_name,
        "s3": {
            "bucket": {"name": bucket},
            "object": {"key": key, "size": size},
        },
    }


def _make_sqs_message(records, receipt_handle="rh-1", sns_wrapped=False):
    inner = {"Records": records}
    body = {"Message": json.dumps(inner)} if sns_wrapped else inner
    return {"Body": json.dumps(body), "ReceiptHandle": receipt_handle}


def test_parse_key_valid(importer_lib):
    assert importer_lib["parse_key"]("test/mytestCase/folder/filename.zip") == (
        ["test", "mytestCase", "folder"],
        "filename.zip",
    )


def test_parse_key_single_segment(importer_lib):
    """A single-folder key mirrors to a single root folder with the file inside."""
    assert importer_lib["parse_key"]("uploads/file.txt") == (
        ["uploads"],
        "file.txt",
    )


def test_parse_key_rejects_no_folder_prefix(importer_lib):
    """A bare filename with no '/' is ambiguous and must be skipped."""
    with pytest.raises(ValueError):
        importer_lib["parse_key"]("just-a-filename.txt")


def test_parse_key_rejects_empty_segment(importer_lib):
    with pytest.raises(ValueError):
        importer_lib["parse_key"]("users//data/file.txt")


@pytest.mark.parametrize(
    "bad_key",
    [
        "users/../file.txt",
        "users/./file.txt",
        "users/case1/..",
        "users/case1/.",
        "users/\\/file.txt",
        "users/case1/\\",
        "users/\x00/file.txt",
        "users/case1/\x00",
    ],
)
def test_parse_key_rejects_unsafe_segments(importer_lib, bad_key):
    """'.', '..', backslash, and NUL are rejected when they are a whole path segment."""
    with pytest.raises(ValueError):
        importer_lib["parse_key"](bad_key)


def test_download_file_from_s3(importer_lib, mocker):
    """Successful download writes to .partial then os.replace()s into place."""
    mock_s3 = mocker.MagicMock()
    mock_replace = mocker.patch("importers.aws.importer.os.replace")

    importer_lib["download_file_from_s3"](
        mock_s3, "my-bucket", "my-object", "/path/to/output"
    )

    mock_s3.download_file.assert_called_once_with(
        "my-bucket", "my-object", "/path/to/output.partial"
    )
    mock_replace.assert_called_once_with("/path/to/output.partial", "/path/to/output")


def test_download_file_from_s3_cleans_up_partial_on_failure(importer_lib, mocker):
    """On download failure, the .partial file is unlinked and the error re-raises."""
    mock_s3 = mocker.MagicMock()
    mock_s3.download_file.side_effect = Exception("network flake")
    mocker.patch("importers.aws.importer.os.path.exists", return_value=True)
    mock_unlink = mocker.patch("importers.aws.importer.os.unlink")

    with pytest.raises(Exception, match="network flake"):
        importer_lib["download_file_from_s3"](
            mock_s3, "my-bucket", "my-object", "/path/to/output"
        )

    mock_unlink.assert_called_once_with("/path/to/output.partial")


def _patch_successful_dependencies(mocker, folder_path="/folder/path", folder_id=7):
    mock_get_or_create_root = mocker.patch(
        "importers.aws.importer.get_or_create_root_folder"
    )
    mock_folder = mocker.MagicMock()
    mock_folder.path = folder_path
    mock_folder.id = folder_id
    mock_get_or_create_root.return_value = mock_folder

    # Subfolder walk returns the same folder stub for every segment; tests only
    # inspect the deepest folder's .id/.path and the sequence of call args.
    mock_get_or_create_sub = mocker.patch(
        "importers.aws.importer.get_or_create_subfolder"
    )
    mock_get_or_create_sub.return_value = mock_folder

    mock_download = mocker.patch("importers.aws.importer.download_file_from_s3")
    mock_create = mocker.patch("importers.aws.importer.create_file_record")
    mock_file_db = mocker.MagicMock()
    mock_file_db.id = 123
    mock_create.return_value = mock_file_db
    mock_hashes = mocker.patch("importers.aws.importer.generate_hashes")

    return {
        "get_or_create_root": mock_get_or_create_root,
        "get_or_create_sub": mock_get_or_create_sub,
        "folder": mock_folder,
        "download": mock_download,
        "create": mock_create,
        "file_db": mock_file_db,
        "hashes": mock_hashes,
    }


def test_process_s3_record_success(importer_lib, mocker):
    patches = _patch_successful_dependencies(mocker)
    mock_db = mocker.MagicMock()

    record = _make_s3_record(
        key="users/mytestCase/data/A_new_file_20261212.ize", size=100
    )

    importer_lib["process_s3_record"](
        mocker.MagicMock(), record, mock_db, _make_robot_user(mocker)
    )

    # Root folder is the first path segment; each remaining segment is a subfolder.
    patches["get_or_create_root"].assert_called_once()
    root_args, _ = patches["get_or_create_root"].call_args
    assert root_args[0] is mock_db
    assert root_args[1] == "users"

    assert patches["get_or_create_sub"].call_count == 2
    sub_segments = [c.args[2] for c in patches["get_or_create_sub"].call_args_list]
    assert sub_segments == ["mytestCase", "data"]

    patches["download"].assert_called_once()
    download_args = patches["download"].call_args.args
    assert download_args[3].startswith("/folder/path/")
    assert download_args[3].endswith(".ize")

    patches["create"].assert_called_once()
    patches["hashes"].assert_called_once_with(123)


def test_process_s3_record_url_encoded_key_is_decoded(importer_lib, mocker):
    """'+' and '%20' should both decode to spaces before parsing."""
    patches = _patch_successful_dependencies(mocker)

    record = _make_s3_record(key="users/case+one/data/my+file%20name.txt")
    importer_lib["process_s3_record"](
        mocker.MagicMock(), record, mocker.MagicMock(), _make_robot_user(mocker)
    )

    # Root is "users"; first subfolder is the decoded "case one".
    assert patches["get_or_create_root"].call_args.args[1] == "users"
    sub_segments = [c.args[2] for c in patches["get_or_create_sub"].call_args_list]
    assert sub_segments == ["case one", "data"]
    # create_file_record(db, filename, file_uuid, file_extension, folder_id, user_id)
    assert patches["create"].call_args.args[1] == "my file name.txt"


@pytest.mark.parametrize(
    "record",
    [
        pytest.param({"eventName": "ObjectCreated:Put"}, id="missing-s3-key"),
        pytest.param(
            {"eventName": "ObjectCreated:Put", "s3": {"object": {"key": "a/b.txt"}}},
            id="missing-bucket",
        ),
        pytest.param(
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "a/b.txt", "size": "huge"},
                },
            },
            id="non-numeric-size",
        ),
    ],
)
def test_process_s3_record_skips_malformed_record(importer_lib, mocker, record):
    """A malformed record must skip cleanly so SQS can delete the message."""
    mock_get_or_create = mocker.patch(
        "importers.aws.importer.get_or_create_root_folder"
    )

    # Must not raise — the caller relies on returning normally.
    importer_lib["process_s3_record"](
        mocker.MagicMock(), record, mocker.MagicMock(), _make_robot_user(mocker)
    )

    mock_get_or_create.assert_not_called()


def test_process_s3_record_skips_directory_marker(importer_lib, mocker):
    mock_get_or_create = mocker.patch(
        "importers.aws.importer.get_or_create_root_folder"
    )

    importer_lib["process_s3_record"](
        mocker.MagicMock(),
        _make_s3_record(key="users/case1/data/"),
        mocker.MagicMock(),
        _make_robot_user(mocker),
    )

    mock_get_or_create.assert_not_called()


def test_process_s3_record_skips_bad_layout(importer_lib, mocker):
    """A key with no '/' has no folder to land in; it must be skipped."""
    mock_get_or_create = mocker.patch(
        "importers.aws.importer.get_or_create_root_folder"
    )

    importer_lib["process_s3_record"](
        mocker.MagicMock(),
        _make_s3_record(key="no-prefix-file.txt"),
        mocker.MagicMock(),
        _make_robot_user(mocker),
    )

    mock_get_or_create.assert_not_called()


def test_process_s3_record_download_error_raises_for_redelivery(importer_lib, mocker):
    """Download failures are often transient; re-raise so SQS redelivers the message."""
    patches = _patch_successful_dependencies(mocker)
    patches["download"].side_effect = Exception("boom")

    with pytest.raises(Exception, match="boom"):
        importer_lib["process_s3_record"](
            mocker.MagicMock(),
            _make_s3_record(key="users/case1/data/file.txt"),
            mocker.MagicMock(),
            _make_robot_user(mocker),
        )

    patches["create"].assert_not_called()


def test_process_s3_record_create_file_error_unlinks_and_raises(importer_lib, mocker):
    """DB insert failures unlink the download and re-raise so SQS redelivers."""
    patches = _patch_successful_dependencies(mocker)
    patches["create"].side_effect = Exception("db down")
    mock_unlink = mocker.patch("importers.aws.importer.os.unlink")

    with pytest.raises(Exception, match="db down"):
        importer_lib["process_s3_record"](
            mocker.MagicMock(),
            _make_s3_record(key="users/case1/data/file.txt"),
            mocker.MagicMock(),
            _make_robot_user(mocker),
        )

    patches["download"].assert_called_once()
    unlinked_paths = [call.args[0] for call in mock_unlink.call_args_list]
    assert any(
        p.endswith(".txt") for p in unlinked_paths
    ), f"expected final file to be unlinked, got {unlinked_paths}"
    patches["hashes"].assert_not_called()


def test_process_s3_record_hash_error_does_not_fail_import(importer_lib, mocker):
    """Hash failures on an already-persisted file must not bubble up and trigger SQS redelivery."""
    patches = _patch_successful_dependencies(mocker)
    patches["hashes"].side_effect = Exception("magic library exploded")

    # Must not raise.
    importer_lib["process_s3_record"](
        mocker.MagicMock(),
        _make_s3_record(key="users/case1/data/file.txt"),
        mocker.MagicMock(),
        _make_robot_user(mocker),
    )

    # File still imported; the hash failure was swallowed with a log.
    patches["create"].assert_called_once()
    patches["hashes"].assert_called_once()


def test_process_s3_record_skips_hashing_for_large_files(importer_lib, mocker):
    patches = _patch_successful_dependencies(mocker)

    # size > HASH_SIZE_LIMIT (10 MB)
    record = _make_s3_record(key="users/case1/data/big.bin", size=20 * 1024 * 1024)
    importer_lib["process_s3_record"](
        mocker.MagicMock(), record, mocker.MagicMock(), _make_robot_user(mocker)
    )

    patches["hashes"].assert_not_called()


def test_process_s3_record_auto_creates_folder_tree(importer_lib, mocker):
    """The importer must mirror the full S3 directory path into the folder tree."""
    patches = _patch_successful_dependencies(mocker)

    importer_lib["process_s3_record"](
        mocker.MagicMock(),
        _make_s3_record(key="users/brand-new-case/data/file.txt"),
        mocker.MagicMock(),
        _make_robot_user(mocker),
    )

    assert patches["get_or_create_root"].call_args.args[1] == "users"
    sub_segments = [c.args[2] for c in patches["get_or_create_sub"].call_args_list]
    assert sub_segments == ["brand-new-case", "data"]
    patches["create"].assert_called_once()


def test_process_s3_record_no_workflow_when_template_id_unset(importer_lib, mocker):
    """With AWS_IMPORT_TEMPLATE_ID unset (default), no workflow is created."""
    patches = _patch_successful_dependencies(mocker)
    mock_run = mocker.patch("importers.aws.importer._run_template_workflow")

    importer_lib["process_s3_record"](
        mocker.MagicMock(),
        _make_s3_record(key="users/case1/data/file.txt"),
        mocker.MagicMock(),
        _make_robot_user(mocker),
    )

    # File still imported, but no workflow machinery touched.
    patches["create"].assert_called_once()
    mock_run.assert_not_called()


def test_process_s3_record_runs_workflow_when_template_id_set(importer_lib, mocker):
    patches = _patch_successful_dependencies(mocker)

    from importers.aws import importer as aws_importer

    mocker.patch.object(aws_importer, "AWS_IMPORT_TEMPLATE_ID", 7)
    mocker.patch.object(
        aws_importer, "AWS_IMPORT_TEMPLATE_PARAMS", {"my_param_0": "value"}
    )

    # Stub the new in-process helpers.
    mock_workflow = mocker.MagicMock(id=42, spec_json='{"workflow": {}}')
    mock_create = mocker.patch(
        "lib.workflow_utils.create_workflow",
        return_value=mock_workflow,
    )
    mock_run = mocker.patch("lib.workflow_utils.run_workflow")

    mock_db = mocker.MagicMock()
    robot_user = _make_robot_user(mocker)

    importer_lib["process_s3_record"](
        mocker.MagicMock(),
        _make_s3_record(key="users/case1/data/file.txt"),
        mock_db,
        robot_user,
    )

    patches["create"].assert_called_once()
    mock_create.assert_called_once_with(
        mock_db,
        folder_id=patches["folder"].id,
        file_ids=[patches["file_db"].id],
        template_id=7,
        template_params={"my_param_0": "value"},
        user=robot_user,
        display_name="file.txt.workflow",
    )
    mock_run.assert_called_once_with(
        mock_db,
        workflow=mock_workflow,
        workflow_spec={"workflow": {}},
        user=robot_user,
    )


def test_process_s3_record_workflow_error_does_not_fail_import(importer_lib, mocker):
    """Failure inside create_workflow must not swallow the file import."""
    patches = _patch_successful_dependencies(mocker)

    from importers.aws import importer as aws_importer

    mocker.patch.object(aws_importer, "AWS_IMPORT_TEMPLATE_ID", 7)
    mocker.patch(
        "lib.workflow_utils.create_workflow",
        side_effect=Exception("db down"),
    )

    importer_lib["process_s3_record"](
        mocker.MagicMock(),
        _make_s3_record(key="users/case1/data/file.txt"),
        mocker.MagicMock(),
        _make_robot_user(mocker),
    )

    # Import still succeeded (file created, hashes triggered).
    patches["create"].assert_called_once()
    patches["hashes"].assert_called_once()


def test_process_s3_record_workflow_error_logs_at_warning_with_traceback(
    importer_lib, mocker, caplog
):
    """Workflow auto-run is best-effort: the failure log must be WARNING
    (not ERROR/.exception) and must still include the traceback, and the
    successful-import log line must still be emitted so operators can tell
    the file was ingested.
    """
    import logging

    _patch_successful_dependencies(mocker)

    from importers.aws import importer as aws_importer

    mocker.patch.object(aws_importer, "AWS_IMPORT_TEMPLATE_ID", 7)
    mocker.patch(
        "lib.workflow_utils.create_workflow",
        side_effect=RuntimeError("workflow machinery exploded"),
    )

    with caplog.at_level(logging.DEBUG, logger="importers.aws.importer"):
        importer_lib["process_s3_record"](
            mocker.MagicMock(),
            _make_s3_record(key="users/case1/data/file.txt"),
            mocker.MagicMock(),
            _make_robot_user(mocker),
        )

    # The failure is logged at WARNING, not ERROR — best-effort path.
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "workflow auto-run failed" in r.getMessage() for r in warning_records
    ), f"expected a WARNING about workflow auto-run; got {caplog.records!r}"

    # The traceback is attached to that WARNING record via exc_info.
    assert any(
        "workflow auto-run failed" in r.getMessage() and r.exc_info is not None
        for r in warning_records
    ), "WARNING record must carry exc_info for debuggability"

    # No ERROR-level record from the workflow path — only the downstream
    # INFO "Imported ... workflow auto-run failed" note.
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert (
        error_records == []
    ), f"workflow failure must not escalate to ERROR: {error_records!r}"

    # The ingest-status log line is still emitted (INFO), so operators can
    # distinguish "file imported, workflow missed" from "file never imported".
    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any(
        "Imported s3://" in r.getMessage()
        and "workflow auto-run failed" in r.getMessage()
        for r in info_records
    ), "expected INFO 'Imported ... workflow auto-run failed' follow-up"


def test_process_s3_record_fans_out_psort_when_slices_configured(
    importer_lib, mocker
):
    """With slicing configured, the spec handed to run_workflow has one psort
    node per slice, each carrying its own filter, each keeping its nested
    export branch."""
    _patch_successful_dependencies(mocker)

    from importers.aws import importer as aws_importer

    psort_name = "openrelik-worker-plaso.tasks.psort"
    export_name = "openrelik-worker-export-splunk.tasks.export"
    template_spec = {
        "workflow": {
            "type": "chain",
            "tasks": [
                {
                    "type": "task",
                    "task_name": psort_name,
                    "uuid": "psort-uuid",
                    "task_config": [],
                    "tasks": [
                        {
                            "type": "task",
                            "task_name": export_name,
                            "uuid": "export-uuid",
                            "task_config": [],
                            "tasks": [],
                        }
                    ],
                }
            ],
        }
    }
    mock_workflow = mocker.MagicMock(id=42, spec_json=json.dumps(template_spec))
    mocker.patch("lib.workflow_utils.create_workflow", return_value=mock_workflow)
    mock_run = mocker.patch("lib.workflow_utils.run_workflow")

    mocker.patch.object(aws_importer, "AWS_IMPORT_TEMPLATE_ID", 7)
    mocker.patch.object(aws_importer, "AWS_IMPORT_PSORT_SLICES", 3)
    mocker.patch.object(aws_importer, "AWS_IMPORT_PSORT_MONTHS_PER_SLICE", 3)

    importer_lib["process_s3_record"](
        mocker.MagicMock(),
        _make_s3_record(key="users/case1/data/file.txt"),
        mocker.MagicMock(),
        _make_robot_user(mocker),
    )

    spec = mock_run.call_args.kwargs["workflow_spec"]
    # psort is the chain's first task, so its clones replace it in-place there.
    psort_nodes = spec["workflow"]["tasks"]
    assert len(psort_nodes) == 3
    filters = [
        next(i["value"] for i in n["task_config"] if i["name"] == "filter")
        for n in psort_nodes
    ]
    assert all("DATETIME(" in f for f in filters)
    assert len(set(filters)) == 3  # each slice a distinct window
    # Each slice keeps its own export branch.
    for node in psort_nodes:
        assert node["tasks"][0]["task_name"] == export_name


def _stub_sqs_message_deps(mocker):
    """Stub database.SessionLocal and get_user_from_db for process_sqs_message tests."""
    mocker.patch("importers.aws.importer.database")
    mocker.patch(
        "importers.aws.importer.get_user_from_db",
        return_value=_make_robot_user(mocker),
    )


def test_process_sqs_message_direct_s3_event(importer_lib, mocker):
    _stub_sqs_message_deps(mocker)
    mock_handler = mocker.patch("importers.aws.importer.process_s3_record")

    record = _make_s3_record()
    importer_lib["process_sqs_message"](mocker.MagicMock(), _make_sqs_message([record]))

    mock_handler.assert_called_once()
    assert mock_handler.call_args.args[1] == record


def test_process_sqs_message_sns_wrapped(importer_lib, mocker):
    _stub_sqs_message_deps(mocker)
    mock_handler = mocker.patch("importers.aws.importer.process_s3_record")

    record = _make_s3_record()
    importer_lib["process_sqs_message"](
        mocker.MagicMock(), _make_sqs_message([record], sns_wrapped=True)
    )

    mock_handler.assert_called_once()
    assert mock_handler.call_args.args[1] == record


def test_process_sqs_message_no_records(importer_lib, mocker):
    """A message with no 'Records' (e.g. s3:TestEvent) must be a no-op."""
    _stub_sqs_message_deps(mocker)
    mock_handler = mocker.patch("importers.aws.importer.process_s3_record")

    message = {"Body": json.dumps({"Event": "s3:TestEvent"}), "ReceiptHandle": "rh"}
    importer_lib["process_sqs_message"](mocker.MagicMock(), message)

    mock_handler.assert_not_called()


def test_process_sqs_message_skips_non_object_created(importer_lib, mocker):
    _stub_sqs_message_deps(mocker)
    mock_handler = mocker.patch("importers.aws.importer.process_s3_record")
    record = _make_s3_record(event_name="ObjectRemoved:Delete")
    importer_lib["process_sqs_message"](mocker.MagicMock(), _make_sqs_message([record]))
    mock_handler.assert_not_called()


def test_process_sqs_message_uses_per_record_session(importer_lib, mocker):
    """Each S3 record in a batched message gets its own SessionLocal + user lookup."""
    mock_db_module = mocker.patch("importers.aws.importer.database")
    mock_get_user = mocker.patch(
        "importers.aws.importer.get_user_from_db",
        return_value=_make_robot_user(mocker),
    )
    mocker.patch("importers.aws.importer.process_s3_record")

    records = [
        _make_s3_record(key="users/case1/data/a.txt"),
        _make_s3_record(key="users/case1/data/b.txt"),
        _make_s3_record(key="users/case1/data/c.txt"),
    ]
    importer_lib["process_sqs_message"](mocker.MagicMock(), _make_sqs_message(records))

    assert mock_db_module.SessionLocal.call_count == 3
    assert mock_get_user.call_count == 3


@pytest.mark.parametrize(
    "message",
    [
        pytest.param(
            {"Body": "{not valid json", "ReceiptHandle": "rh"}, id="invalid-json"
        ),
        pytest.param(
            {
                "Body": json.dumps({"Message": "{still invalid"}),
                "ReceiptHandle": "rh",
            },
            id="sns-wrapped-invalid-inner",
        ),
        pytest.param({"ReceiptHandle": "rh"}, id="missing-body-key"),
    ],
)
def test_process_sqs_message_malformed_body_is_noop(importer_lib, mocker, message):
    """Malformed bodies must drop cleanly (no handler call, no exception) so SQS can delete the message."""
    _stub_sqs_message_deps(mocker)
    mock_handler = mocker.patch("importers.aws.importer.process_s3_record")

    # Must not raise — the caller relies on returning normally to delete the message.
    importer_lib["process_sqs_message"](mocker.MagicMock(), message)

    mock_handler.assert_not_called()


def test_main_malformed_body_is_deleted(importer_lib, mocker):
    """End-to-end: a malformed SQS body is deleted, not looped."""
    mocker.patch("importers.aws.importer.ROBOT_ACCOUNT_USER_ID", 1)
    mocker.patch("importers.aws.importer.SQS_QUEUE_URL", "https://sqs.example/queue")

    mock_sqs, _ = _stub_main_dependencies(mocker)

    bad_message = {"Body": "{not json", "ReceiptHandle": "rh-bad"}
    mock_sqs.receive_message.side_effect = [
        {"Messages": [bad_message]},
        KeyboardInterrupt(),
    ]

    with pytest.raises(KeyboardInterrupt):
        importer_lib["main"]()

    mock_sqs.delete_message.assert_called_once_with(
        QueueUrl="https://sqs.example/queue", ReceiptHandle="rh-bad"
    )


def test_process_sqs_message_multiple_records(importer_lib, mocker):
    _stub_sqs_message_deps(mocker)
    mock_handler = mocker.patch("importers.aws.importer.process_s3_record")

    records = [
        _make_s3_record(key="users/case1/data/a.txt"),
        _make_s3_record(
            key="users/case1/data/b.txt", event_name="ObjectRemoved:Delete"
        ),
        _make_s3_record(key="users/case1/data/c.txt"),
    ]
    importer_lib["process_sqs_message"](mocker.MagicMock(), _make_sqs_message(records))

    assert mock_handler.call_count == 2


def test_main_no_robot_user(importer_lib, mocker):
    mocker.patch("importers.aws.importer.ROBOT_ACCOUNT_USER_ID", None)
    mock_boto = mocker.patch("importers.aws.importer.boto3.client")

    importer_lib["main"]()

    mock_boto.assert_not_called()


def test_main_no_queue_url(importer_lib, mocker):
    mocker.patch("importers.aws.importer.ROBOT_ACCOUNT_USER_ID", 1)
    mocker.patch("importers.aws.importer.SQS_QUEUE_URL", None)
    mock_boto = mocker.patch("importers.aws.importer.boto3.client")

    importer_lib["main"]()

    mock_boto.assert_not_called()


def _stub_main_dependencies(mocker, robot_user=None, template=None):
    """Stub boto3, database, get_user_from_db, and the template lookup for main() tests."""
    mock_sqs = mocker.MagicMock()
    mock_s3 = mocker.MagicMock()
    mocker.patch(
        "importers.aws.importer.boto3.client",
        side_effect=lambda s, **_: {"sqs": mock_sqs, "s3": mock_s3}[s],
    )
    mocker.patch("importers.aws.importer.database")
    mocker.patch(
        "importers.aws.importer.get_user_from_db",
        return_value=robot_user if robot_user is not None else _make_robot_user(mocker),
    )
    # Default: pretend any template id resolves, so tests that don't care about
    # template validation aren't forced to configure it.
    mocker.patch(
        "importers.aws.importer.get_workflow_template_from_db",
        return_value=template if template is not None else mocker.MagicMock(),
    )
    return mock_sqs, mock_s3


def test_main_processes_message_and_deletes(importer_lib, mocker):
    mocker.patch("importers.aws.importer.ROBOT_ACCOUNT_USER_ID", 1)
    mocker.patch("importers.aws.importer.SQS_QUEUE_URL", "https://sqs.example/queue")

    mock_sqs, _ = _stub_main_dependencies(mocker)

    message = _make_sqs_message([_make_s3_record()], receipt_handle="rh-42")
    mock_sqs.receive_message.side_effect = [
        {"Messages": [message]},
        KeyboardInterrupt(),
    ]

    mock_process = mocker.patch("importers.aws.importer.process_sqs_message")

    with pytest.raises(KeyboardInterrupt):
        importer_lib["main"]()

    mock_process.assert_called_once()
    # Delete MUST follow a successful process — regression from an earlier
    # rewrite that dropped this assertion. Without it, a code change that
    # stops calling delete_message wouldn't be caught here.
    mock_sqs.delete_message.assert_called_once_with(
        QueueUrl="https://sqs.example/queue", ReceiptHandle="rh-42"
    )


def test_main_processing_error_does_not_delete(importer_lib, mocker):
    mocker.patch("importers.aws.importer.ROBOT_ACCOUNT_USER_ID", 1)
    mocker.patch("importers.aws.importer.SQS_QUEUE_URL", "https://sqs.example/queue")

    mock_sqs, _ = _stub_main_dependencies(mocker)

    message = _make_sqs_message([_make_s3_record()])
    mock_sqs.receive_message.side_effect = [
        {"Messages": [message]},
        KeyboardInterrupt(),
    ]

    mocker.patch(
        "importers.aws.importer.process_sqs_message",
        side_effect=Exception("processing failed"),
    )

    with pytest.raises(KeyboardInterrupt):
        importer_lib["main"]()

    mock_sqs.delete_message.assert_not_called()


def test_main_receive_error_retries(importer_lib, mocker):
    mocker.patch("importers.aws.importer.ROBOT_ACCOUNT_USER_ID", 1)
    mocker.patch("importers.aws.importer.SQS_QUEUE_URL", "https://sqs.example/queue")

    mock_sqs, _ = _stub_main_dependencies(mocker)
    mock_sleep = mocker.patch("importers.aws.importer.time.sleep")

    mock_sqs.receive_message.side_effect = [
        Exception("transient"),
        KeyboardInterrupt(),
    ]

    with pytest.raises(KeyboardInterrupt):
        importer_lib["main"]()

    mock_sleep.assert_called_once_with(5)


def test_main_empty_receive_keeps_polling(importer_lib, mocker):
    mocker.patch("importers.aws.importer.ROBOT_ACCOUNT_USER_ID", 1)
    mocker.patch("importers.aws.importer.SQS_QUEUE_URL", "https://sqs.example/queue")

    mock_sqs, _ = _stub_main_dependencies(mocker)

    mock_process = mocker.patch("importers.aws.importer.process_sqs_message")
    mock_sqs.receive_message.side_effect = [
        {"Messages": []},
        KeyboardInterrupt(),
    ]

    with pytest.raises(KeyboardInterrupt):
        importer_lib["main"]()

    mock_process.assert_not_called()
    mock_sqs.delete_message.assert_not_called()


def test_main_no_robot_user_in_db(importer_lib, mocker):
    """ROBOT_ACCOUNT_USER_ID set but no matching user row -> abort before polling."""
    mocker.patch("importers.aws.importer.ROBOT_ACCOUNT_USER_ID", 99999)
    mocker.patch("importers.aws.importer.SQS_QUEUE_URL", "https://sqs.example/queue")

    mock_boto = mocker.patch("importers.aws.importer.boto3.client")
    mocker.patch("importers.aws.importer.database")
    mocker.patch("importers.aws.importer.get_user_from_db", return_value=None)
    mocker.patch(
        "importers.aws.importer.get_workflow_template_from_db",
        return_value=mocker.MagicMock(),
    )

    importer_lib["main"]()

    mock_boto.assert_not_called()


def test_main_no_template_in_db(importer_lib, mocker):
    """AWS_IMPORT_TEMPLATE_ID set but no matching template row -> abort before polling."""
    mocker.patch("importers.aws.importer.ROBOT_ACCOUNT_USER_ID", 1)
    mocker.patch("importers.aws.importer.SQS_QUEUE_URL", "https://sqs.example/queue")
    mocker.patch("importers.aws.importer.AWS_IMPORT_TEMPLATE_ID", 9999)

    mock_boto = mocker.patch("importers.aws.importer.boto3.client")
    mocker.patch("importers.aws.importer.database")
    mocker.patch(
        "importers.aws.importer.get_user_from_db",
        return_value=_make_robot_user(mocker),
    )
    mock_template_lookup = mocker.patch(
        "importers.aws.importer.get_workflow_template_from_db",
        return_value=None,
    )

    importer_lib["main"]()

    mock_boto.assert_not_called()
    mock_template_lookup.assert_called_once()


def test_main_skips_template_lookup_when_disabled(importer_lib, mocker):
    """With AWS_IMPORT_TEMPLATE_ID unset, no template DB lookup happens at startup."""
    mocker.patch("importers.aws.importer.ROBOT_ACCOUNT_USER_ID", 1)
    mocker.patch("importers.aws.importer.SQS_QUEUE_URL", "https://sqs.example/queue")
    mocker.patch("importers.aws.importer.AWS_IMPORT_TEMPLATE_ID", None)

    mock_sqs, _ = _stub_main_dependencies(mocker)
    mock_template_lookup = mocker.patch(
        "importers.aws.importer.get_workflow_template_from_db"
    )
    mock_sqs.receive_message.side_effect = [KeyboardInterrupt()]

    with pytest.raises(KeyboardInterrupt):
        importer_lib["main"]()

    mock_template_lookup.assert_not_called()
