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
from lib.workflow_utils import update_task_config_values, add_unique_parameter_names

def test_update_task_config_values():
    """Test update_task_config_values updates values correctly."""
    data = {
        "task_config": [
            {"param_name": "param_1", "value": "old_value_1"},
            {"param_name": "param_2", "value": "old_value_2"},
        ],
        "sub_item": {
            "task_config": [
                {"param_name": "param_1", "value": "old_value_3"}, # Same param_name, updates too
            ]
        }
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
        {
            "task_config": [{"param_name": "param_1", "value": "old"}]
        },
        {
            "task_config": [{"param_name": "param_1", "value": "old"}]
        }
    ]
    
    parameters = {"param_1": "new"}
    
    update_task_config_values(data, parameters)
    
    assert data[0]["task_config"][0]["value"] == "new"
    assert data[1]["task_config"][0]["value"] == "new"

def test_add_unique_parameter_names():
    """Test add_unique_parameter_names generates unique names."""
    data = {
        "task_config": [
            {"name": "Parameter One"},
            {"name": "Parameter One"},
            {"name": "Parameter Two"},
        ],
        "sub_item": {
            "task_config": [
                {"name": "Parameter One"},
            ]
        }
    }
    
    add_unique_parameter_names(data)
    
    assert data["task_config"][0]["param_name"] == "parameter_one_0"
    assert data["task_config"][1]["param_name"] == "parameter_one_1"
    assert data["task_config"][2]["param_name"] == "parameter_two_0"
    assert data["sub_item"]["task_config"][0]["param_name"] == "parameter_one_2"

def test_add_unique_parameter_names_no_name():
    """Test add_unique_parameter_names ignores items without name."""
    data = {
        "task_config": [
            {"value": "only value"},
        ]
    }
    
    add_unique_parameter_names(data)
    
    assert "param_name" not in data["task_config"][0]
