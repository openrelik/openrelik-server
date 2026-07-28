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

"""Tests for the background file hashing Celery task."""

from tasks.hashing import file_hashes_tasks


def test_generate_hashes_task_delegates(mocker):
    """The task delegates to lib.file_hashes.generate_hashes with the file id."""
    mock_generate_hashes = mocker.patch("tasks.hashing.file_hashes_tasks.generate_hashes")

    file_hashes_tasks.generate_hashes_task(42)

    mock_generate_hashes.assert_called_once_with(42)


def test_task_name_prefix_matches_queue():
    """Routing relies on the task name prefix equalling the queue name."""
    assert file_hashes_tasks.TASK_NAME.split(".")[0] == file_hashes_tasks.QUEUE_NAME
