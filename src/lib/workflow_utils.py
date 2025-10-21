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

from collections import defaultdict


def update_task_config_values(data: dict | list, parameters: dict) -> None:
    """
    Recursively traverses a dictionary or list to find 'task_config' lists
    and updates the 'value' of each item based on the unique 'param_name'.

    Args:
        data (dict | list): The dictionary or list to traverse.
        parameters (dict): A dictionary where keys are the unique 'param_name'.
    """
    if isinstance(data, dict):
        task_config = data.get("task_config", [])
        for item in task_config:
            param_name = item.get("param_name")
            if not param_name:
                continue

            if param_name in parameters:
                item["value"] = parameters[param_name]
                continue

        for key, value in data.items():
            update_task_config_values(value, parameters)

    elif isinstance(data, list):
        for item in data:
            update_task_config_values(item, parameters)


def add_unique_parameter_names(data: dict | list) -> None:
    """
    Wrapper function to initiate the recursive traversal with a shared counter.

    Args:
        data (dict | list): The workflow dictionary to modify.
    """
    _add_unique_parameter_names_recursive(data, defaultdict(int))


def _add_unique_parameter_names_recursive(data: dict | list, counts: defaultdict) -> None:
    """
    Recursively traverses a workflow dictionary and adds a unique
    "param_name" key to each task_config item that has a "name" key.
    The "param_name" is created by lowercasing the original name and
    replacing spaces with underscores, followed by a unique index.

    Args:
        data (dict | list): The workflow dictionary to modify.
        counts (defaultdict): A dictionary to keep track of the counts of each normalized name.
    """
    if isinstance(data, dict):
        if "task_config" in data and isinstance(data["task_config"], list):
            for item in data["task_config"]:
                if "name" in item:
                    normalized_name = item["name"].lower().replace(" ", "_")
                    param_name = f"{normalized_name}_{counts[normalized_name]}"
                    item["param_name"] = param_name
                    counts[normalized_name] += 1

        for key, value in data.items():
            _add_unique_parameter_names_recursive(value, counts)

    elif isinstance(data, list):
        for item in data:
            _add_unique_parameter_names_recursive(item, counts)
