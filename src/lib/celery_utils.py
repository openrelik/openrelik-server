# Copyright 2024 Google LLC
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

import ast
import re


def get_registered_celery_tasks(celery_instance):
    """Get a list of registered celery tasks.

    Args:
        celery_instance (Celery): A celery instance.

    Returns:
        list: A list of registered celery tasks.
    """
    registered_celery_tasks = celery_instance.control.inspect().registered("metadata")
    registered_task_names = set()
    registered_tasks_formatted = []

    # If no Celery workers are currently active, return an empty list.
    if not registered_celery_tasks:
        return []

    for _, tasks in registered_celery_tasks.items():
        for task in tasks:
            task_name = task.split()[0]
            # Extract metadata embedded within the task string.
            # Metadata is stored as a Python dictionary enclosed in curly braces within the string.
            # This regular expression captures the entire dictionary using curly braces as delimiters.
            # group(0) retrieves the full match, i.e., the dictionary string.
            # ast.literal_eval() safely converts the dictionary string into an actual Python dictionary object.
            metadata = ast.literal_eval(re.search("({.+})", task).group(0))
            if task_name in registered_task_names:
                continue

            # Create a dictionary for task information
            task_info = {"task_name": task_name, "queue_name": task_name.split(".")[0]}

            # Merge metadata into task information
            task_info.update(metadata)  # Extend with metadata

            # Add the enriched task information to the list
            registered_tasks_formatted.append(task_info)

            registered_task_names.add(task_name)
    return registered_tasks_formatted


def update_celery_task_queues(celery_instance):
    """Update the task queues for the celery instance.

    Args:
        celery_instance (Celery): The celery instance.
    """
    registered_tasks = get_registered_celery_tasks(celery_instance)
    task_routes = {}
    for task in registered_tasks:
        task_routes[task.get("task_name")] = {"queue": task.get("queue_name")}
    celery_instance.conf.task_routes = task_routes
