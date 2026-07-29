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

"""Celery task for generating file hashes in the background.

This runs in the dedicated ``openrelik-hashing`` Celery worker (built from the
server image) so that callers such as the mediator can offload the blocking,
potentially long-running hashing work instead of computing hashes inline.

Callers dispatch the task with an explicit ``queue="openrelik-hashing"`` and the
worker consumes that same queue (``-Q openrelik-hashing``).
"""

import os

from celery.app import Celery
from openrelik_common import telemetry

from lib.file_hashes import generate_hashes

QUEUE_NAME = "openrelik-hashing"
TASK_NAME = f"{QUEUE_NAME}.tasks.generate_hashes"

REDIS_URL = os.getenv("REDIS_URL") or "redis://localhost:6379/0"

celery = Celery(
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.hashing.file_hashes_tasks"],
)

telemetry.instrument_celery_app(celery)


@celery.task(name=TASK_NAME)
def generate_hashes_task(file_id):
    """Generate MD5, SHA1, and SHA256 hashes for a file.

    Args:
        file_id (int): The ID of the file in the database.
    """
    generate_hashes(file_id)
