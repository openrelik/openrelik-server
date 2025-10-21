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

import pytest

from lib.workflow_utils import add_unique_parameter_names, update_task_config_values


@pytest.fixture
def template_data():
    test_template_str = '{"workflow": {"type": "chain", "isRoot": true, "tasks": [{"task_name": "openrelik-worker-strings.tasks.strings", "queue_name": "openrelik-worker-strings", "display_name": "Strings", "description": "Extract strings from files", "task_config": [{"name": "UTF16LE", "label": "Extract Unicode strings", "description": "This will tell the strings command to extract UTF-16LE (little endian) encoded strings", "type": "checkbox", "value": true}, {"name": "ASCII", "label": "Extract ASCII strings", "description": "This will tell the strings command to extract ASCII (single-7-bit-byte) encoded strings", "type": "checkbox", "value": false}], "type": "task", "uuid": "e1e6703d5724474aa2a509e9de605430", "tasks": []}, {"task_name": "openrelik-worker-strings.tasks.strings", "queue_name": "openrelik-worker-strings", "display_name": "Strings", "description": "Extract strings from files", "task_config": [{"name": "UTF16LE", "label": "Extract Unicode strings", "description": "This will tell the strings command to extract UTF-16LE (little endian) encoded strings", "type": "checkbox", "value": true}, {"name": "ASCII", "label": "Extract ASCII strings", "description": "This will tell the strings command to extract ASCII (single-7-bit-byte) encoded strings", "type": "checkbox", "value": false}], "type": "task", "uuid": "736a973ffae24081a75abd1d22b8633c", "tasks": []}]}}'
    return json.loads(test_template_str)


def test_add_unique_parameter_names(template_data):
    """
    Tests that add_unique_parameter_names correctly adds unique param_name keys.
    """
    add_unique_parameter_names(template_data)

    # Check the first task's config
    first_task_config = template_data["workflow"]["tasks"][0]["task_config"]
    assert "param_name" in first_task_config[0]
    assert first_task_config[0]["param_name"] == "utf16le_0"
    assert "param_name" in first_task_config[1]
    assert first_task_config[1]["param_name"] == "ascii_0"

    # Check the second task's config to ensure uniqueness
    second_task_config = template_data["workflow"]["tasks"][1]["task_config"]
    assert "param_name" in second_task_config[0]
    assert second_task_config[0]["param_name"] == "utf16le_1"
    assert "param_name" in second_task_config[1]
    assert second_task_config[1]["param_name"] == "ascii_1"


def test_update_task_config_values(template_data):
    """
    Tests that update_task_config_values correctly updates the 'value' based on parameters.
    """
    # First, add the unique parameter names to have a key to update
    add_unique_parameter_names(template_data)

    # Define the parameters to update
    parameters = {"utf16le_0": False, "ascii_0": True, "utf16le_1": False, "ascii_1": True}

    # Update the values
    update_task_config_values(template_data, parameters)

    # Check the updated values for the first task
    first_task_config = template_data["workflow"]["tasks"][0]["task_config"]
    assert first_task_config[0]["value"] is False
    assert first_task_config[1]["value"] is True

    # Check the updated values for the second task
    second_task_config = template_data["workflow"]["tasks"][1]["task_config"]
    assert second_task_config[0]["value"] is False
    assert second_task_config[1]["value"] is True


def test_update_with_missing_param_name(template_data):
    """
    Tests that update_task_config_values gracefully handles a missing param_name in the parameters.
    """
    add_unique_parameter_names(template_data)

    parameters = {
        "utf16le_0": False,
        "ascii_0": True,
    }

    # Update the values with a subset of parameters
    update_task_config_values(template_data, parameters)

    # Check that the specified values are updated
    first_task_config = template_data["workflow"]["tasks"][0]["task_config"]
    assert first_task_config[0]["value"] is False
    assert first_task_config[1]["value"] is True

    # Check that the second task's values remain unchanged because their param_names weren't in the parameters dict
    second_task_config = template_data["workflow"]["tasks"][1]["task_config"]
    assert second_task_config[0]["value"] is True
    assert second_task_config[1]["value"] is False
