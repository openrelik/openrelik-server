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
import json

from unittest import mock

from lib.workflow_utils import (
    TemplateNotFoundError,
    create_workflow,
    replace_uuids,
    run_workflow,
    update_task_config_values,
)


def test_update_task_config_values():
    """Test update_task_config_values updates values correctly."""
    data = {
        "task_config": [
            {"param_name": "param_1", "value": "old_value_1"},
            {"param_name": "param_2", "value": "old_value_2"},
        ],
        "sub_item": {
            "task_config": [
                {
                    "param_name": "param_1",
                    "value": "old_value_3",
                },  # Same param_name, updates too
            ]
        },
    }

    parameters = {
        "param_1": "new_value_1",
        "param_2": "new_value_2",
    }

    update_task_config_values(data, parameters)

    assert data["task_config"][0]["value"] == "new_value_1"
    assert data["task_config"][1]["value"] == "new_value_2"
    assert data["sub_item"]["task_config"][0]["value"] == "new_value_1"


def test_update_task_config_values_list():
    """Test update_task_config_values with a list of items."""
    data = [
        {"task_config": [{"param_name": "param_1", "value": "old"}]},
        {"task_config": [{"param_name": "param_1", "value": "old"}]},
    ]

    parameters = {"param_1": "new"}

    update_task_config_values(data, parameters)

    assert data[0]["task_config"][0]["value"] == "new"
    assert data[1]["task_config"][0]["value"] == "new"


def test_replace_uuids_generates_fresh_uuids():
    data = {"uuid": "OLD", "inner": {"uuid": "OLD"}, "list": [{"uuid": "OLD"}]}
    replace_uuids(data)
    assert data["uuid"] != "OLD"
    assert data["inner"]["uuid"] != "OLD"
    assert data["list"][0]["uuid"] != "OLD"


def test_replace_uuids_with_explicit_value():
    data = {"uuid": "OLD", "inner": {"uuid": "OLD"}}
    replace_uuids(data, replace_with="PLACEHOLDER")
    assert data["uuid"] == "PLACEHOLDER"


def _make_user(user_id=42):
    user = mock.Mock()
    user.id = user_id
    return user


def test_create_workflow_with_template(mocker):
    mock_template = mock.Mock()
    mock_template.id = 7
    mock_template.display_name = "My Template"
    mock_template.spec_json = json.dumps(
        {
            "uuid": "SEED",
            "workflow": {"task_config": [{"param_name": "p", "value": None}]},
        }
    )
    mock_folder = mock.Mock(id=99)
    mock_workflow = mock.Mock()

    mocker.patch(
        "lib.workflow_utils.get_workflow_template_from_db", return_value=mock_template
    )
    mock_create_folder = mocker.patch(
        "lib.workflow_utils.create_subfolder_in_db", return_value=mock_folder
    )
    mock_create_workflow = mocker.patch(
        "lib.workflow_utils.create_workflow_in_db", return_value=mock_workflow
    )

    result = create_workflow(
        db=mock.Mock(),
        folder_id=3,
        file_ids=[1, 2],
        template_id=7,
        template_params={"p": "applied"},
        user=_make_user(),
    )

    assert result is mock_workflow
    mock_create_folder.assert_called_once()
    created_schema = mock_create_workflow.call_args.args[1]
    # The spec was deserialized, uuids replaced, params applied, and re-serialized.
    rendered = json.loads(created_schema.spec_json)
    assert rendered["uuid"] != "SEED"
    assert rendered["workflow"]["task_config"][0]["value"] == "applied"
    assert created_schema.template_id == 7
    assert created_schema.display_name == "My Template"


def test_create_workflow_without_template(mocker):
    mock_folder = mock.Mock(id=99)
    mock_workflow = mock.Mock()
    mocker.patch("lib.workflow_utils.create_subfolder_in_db", return_value=mock_folder)
    mock_create_workflow = mocker.patch(
        "lib.workflow_utils.create_workflow_in_db", return_value=mock_workflow
    )

    result = create_workflow(
        db=mock.Mock(),
        folder_id=3,
        file_ids=[],
        template_id=None,
        template_params=None,
        user=_make_user(),
    )
    assert result is mock_workflow
    created_schema = mock_create_workflow.call_args.args[1]
    assert created_schema.display_name == "Untitled workflow"
    assert created_schema.spec_json is None
    assert created_schema.template_id is None


def test_create_workflow_raises_when_template_missing(mocker):
    mocker.patch("lib.workflow_utils.get_workflow_template_from_db", return_value=None)
    with pytest.raises(TemplateNotFoundError):
        create_workflow(
            db=mock.Mock(),
            folder_id=3,
            file_ids=[],
            template_id=999,
            template_params=None,
            user=_make_user(),
        )


def test_run_workflow_persists_spec_and_dispatches(mocker, tmp_path):
    fake_file = mock.Mock()
    fake_file.id = 1
    fake_file.uuid.hex = "abc"
    fake_file.display_name = "x"
    fake_file.extension = ".txt"
    fake_file.data_type = "dt"
    fake_file.magic_mime = "text/plain"
    fake_file.path = "/tmp/x"

    workflow = mock.Mock()
    workflow.files = [fake_file]
    workflow.folder.path = str(tmp_path / "output")  # will need to be created

    mock_signature = mock.Mock()
    mocker.patch(
        "lib.workflow_utils.create_workflow_signature", return_value=mock_signature
    )

    spec = {"workflow": {"type": "chain", "tasks": []}}
    db = mock.Mock()

    result = run_workflow(db, workflow=workflow, workflow_spec=spec, user=_make_user())

    # spec was persisted to the workflow before dispatch
    assert workflow.spec_json == json.dumps(spec)
    mock_signature.apply_async.assert_called_once()
    # output directory was created on demand
    assert (tmp_path / "output").is_dir()
    # DB round-trip completed
    db.add.assert_called_once_with(workflow)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(workflow)
    assert result is workflow
