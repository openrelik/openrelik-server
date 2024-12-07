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
from prometheus_client.core import CounterMetricFamily
from prometheus_client.registry import Collector

PROMETHEUS_REGISTRY = CollectorRegistry(auto_describe=True)

DEFAULT_LABELS = ["task_name", "hostname"]
TASK_METRICS_MAPPING = {
    "task-sent": {
        "name": "task_sent",
        "description": "Sent when a task message is published.",
    },
    "task-received": {
        "name": "task_received",
        "description": "Sent when the worker receives a task.",
    },
    "task-started": {
        "name": "task_started",
        "description": "Sent just before the worker executes the task.",
    },
    "task-succeeded": {
        "name": "task_succeeded",
        "description": "Sent if the task executed successfully.",
    },
    "task-failed": {
        "name": "task_failed",
        "description": "Sent if the execution of the task failed.",
    },
    "task-rejected": {
        "name": "task_rejected",
        "description": "The task was rejected by the worker, possibly to be re-queued or moved to a dead letter queue.",
    },
    "task-revoked": {
        "name": "task_revoked",
        "description": "Sent if the task has been revoked.",
    },
    "task-retried": {
        "name": "task_retried",
        "description": "Sent if the task failed, but will be retried in the future.",
    },
}

# Initialize task metrics counters with dynamic labels
TASK_METRICS_COUNTERS = {
    event_type: Counter(
        f"celery_{config['name']}",
        config["description"],
        DEFAULT_LABELS + config.get("extra_labels", []),  # Allow extra labels
        registry=PROMETHEUS_REGISTRY,
    )
    for event_type, config in TASK_METRICS_MAPPING.items()
}

# Metrics for task runtime
celery_task_runtime = Histogram(
    "celery_task_runtime",
    "Histogram of task runtime measurements.",
    DEFAULT_LABELS,
    registry=PROMETHEUS_REGISTRY,
)


def get_queue_lengths(celery_app):
    """Retrieves the lengths of all active queues."""
    queues = celery_app.control.inspect().active_queues() or {}
    with celery_app.connection() as connection:
        for _, info_list in queues.items():
            for queue_info in info_list:
                queue_name = queue_info["name"]
                queue_length = connection.default_channel.client.llen(queue_name)
                yield queue_name, queue_length


class QueueMetricsCollector(Collector):
    """Collector for Celery task queue.

    This collector retrieves the lengths of Celery task queues (bumber of tasks in the
    queue) and exposes them as a Prometheus Counter metric named `celery_queue_length`.

    It uses the provided Celery app instance to connect to the broker
    and fetch queue lengths.
    """

    def __init__(self, celery_app):
        self.celery_app = celery_app

    def collect(self):
        metric = CounterMetricFamily(
            "celery_queue_length",
            "The number of messages in the queue.",
            labels=["queue_name"],
        )
        for queue_name, queue_length in get_queue_lengths(self.celery_app):
            metric.add_metric(labels=[queue_name], value=queue_length)
        yield metric


def get_hostname(task_hostname: str) -> str:
    """Extract hostname from worker name."""
    _, hostname = nodesplit(task_hostname)
    return hostname


def handle_worker_event(event):
    """Generic worker event handling."""
    if event.get("type") != "worker-heartbeat":  # Avoid redundant heartbeat messages
        print(f"MONITOR WORKER: Event.type {event.get('type')}")


def handle_task_event(event, state):
    """Handles task events from Celery."""
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
    """Starts the Prometheus metrics exporter."""
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
        start_http_server(registry=PROMETHEUS_REGISTRY, port=8080)
        recv = celery_app.events.Receiver(connection, handlers=handlers)
        recv.capture(limit=None, timeout=None, wakeup=True)


if __name__ == "__main__":
    redis_url = os.getenv("REDIS_URL")
    celery_app = Celery(broker=redis_url, backend=redis_url)

    # Register the queue metrics collector
    PROMETHEUS_REGISTRY.register(QueueMetricsCollector(celery_app))

    run_metrics_exporter(celery_app)
