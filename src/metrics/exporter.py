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

import os

from celery import Celery
from celery.utils import nodesplit
from prometheus_client import CollectorRegistry, Counter, Histogram, start_http_server

METRICS_PREFIX = "celery"
PROMETHEUS_REGISTRY = CollectorRegistry(auto_describe=True)

DEFAULT_LABELS = ["task_name", "hostname"]
TASK_METRICS_MAPPING = {
    "task-sent": {
        "name": "task_sent",
        "description": "Sent when a task message is published.",
        "labels": DEFAULT_LABELS,
    },
    "task-received": {
        "name": "task_received",
        "description": "Sent when the worker receives a task.",
        "labels": DEFAULT_LABELS,
    },
    "task-started": {
        "name": "task_started",
        "description": "Sent just before the worker executes the task.",
        "labels": DEFAULT_LABELS,
    },
    "task-succeeded": {
        "name": "task_succeeded",
        "description": "Sent if the task executed successfully.",
        "labels": DEFAULT_LABELS,
    },
    "task-failed": {
        "name": "task_failed",
        "description": "Sent if the execution of the task failed.",
        "labels": DEFAULT_LABELS,
    },
    "task-rejected": {
        "name": "task_rejected",
        "description": "The task was rejected by the worker, possibly to be re-queued or moved to a dead letter queue.",
        "labels": DEFAULT_LABELS,
    },
    "task-revoked": {
        "name": "task_revoked",
        "description": "Sent if the task has been revoked.",
        "labels": DEFAULT_LABELS,
    },
    "task-retried": {
        "name": "task_retried",
        "description": "Sent if the task failed, but will be retried in the future.",
        "labels": DEFAULT_LABELS,
    },
}

TASK_METRICS_COUNTERS = {}
for event_type, config in TASK_METRICS_MAPPING.items():
    TASK_METRICS_COUNTERS[event_type] = Counter(
        f"{METRICS_PREFIX}_{config['name']}",
        config["description"],
        config["labels"],
        registry=PROMETHEUS_REGISTRY,
    )

# Metrics for other things than task counters.
celery_task_runtime = Histogram(
    f"{METRICS_PREFIX}_task_runtime",
    "Histogram of task runtime measurements.",
    DEFAULT_LABELS,
    registry=PROMETHEUS_REGISTRY,
)


def get_hostname(name: str) -> str:
    """Extract hostname from worker name."""
    _, hostname = nodesplit(name)
    return hostname


def handle_worker_event(event):
    # Generic worker event handling (currently just prints)
    if event.get("type") != "worker-heartbeat":  # Avoid redundant heartbeat messages
        print(f"MONITOR WORKER: Event.type {event.get('type')}")


def handle_task_event(event, state):
    state.event(event)
    task = state.tasks.get(event["uuid"])
    event_type = event.get("type")

    counter = TASK_METRICS_COUNTERS.get(event_type)
    if counter:
        labels = {"task_name": task.name, "hostname": get_hostname(task.hostname)}
        counter.labels(**labels).inc()

        if event_type == "task-succeeded":
            celery_task_runtime.labels(**labels).observe(task.runtime)

        # TODO: For "task-failed", add a label with the exception class name


def run_metrics_exporter(celery_app):
    state = celery_app.events.State()

    handlers = {
        "worker-heartbeat": handle_worker_event,
        "worker-online": handle_worker_event,
        "worker-offline": handle_worker_event,
    }
    handlers.update(
        {
            key: lambda event: handle_task_event(event, state)
            for key in TASK_METRICS_COUNTERS
        }
    )

    with celery_app.connection() as connection:
        start_http_server(registry=PROMETHEUS_REGISTRY, port=8000)
        recv = celery_app.events.Receiver(connection, handlers=handlers)
        recv.capture(limit=None, timeout=None, wakeup=True)


if __name__ == "__main__":
    redis_url = os.getenv("REDIS_URL")
    celery_app = Celery(broker=redis_url, backend=redis_url)
    run_metrics_exporter(celery_app)
