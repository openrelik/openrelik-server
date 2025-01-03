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
from datetime import datetime, timedelta

import requests
from fastapi import APIRouter

from .schemas import MetricsRequest

router = APIRouter()


def calculate_time_range(range: int) -> tuple[float, float]:
    """Calculates start and end timestamps for a given time range in seconds.

    Args:
        range: The number of seconds in the time range.

    Returns:
        A tuple containing the start and end timestamps as floats (Unix timestamps).
    """
    end_time = datetime.now()
    start_time = end_time - timedelta(seconds=range)
    return (start_time.timestamp(), end_time.timestamp())


def query_prometheus_range(query: str, range: int = 3600, step: int = 60) -> dict:
    """Queries Prometheus for data over a given time range.

    Args:
        query: The Prometheus query string.
        range: The time to look back in seconds. Defaults to 3600 (1 hour).
        step: The query resolution step in seconds. Defaults to 60.

    Returns:
        The JSON response from Prometheus as a dictionary.

    Raises:
        requests.exceptions.HTTPError: If the Prometheus query fails.
    """
    prometheus_url_env = os.environ.get("PROMETHEUS_SERVER_URL")
    prometheus_url = f"{prometheus_url_env}/api/v1/query_range"
    start_timestamp, end_timestamp = calculate_time_range(range)
    response = requests.get(
        prometheus_url,
        params={
            "query": query,
            "step": step,
            "start": start_timestamp,
            "end": end_timestamp,
        },
    )
    response.raise_for_status()
    return response.json()


def format_prometheus_data(prometheus_response: dict) -> list[dict]:
    """Formats Prometheus range query response data for charting.

    Args:
        prometheus_response: The JSON response from a Prometheus range query.

    Returns:
        A list of dictionaries, where each dictionary represents a time series
        with 'name' and 'data'. 'data' is a list of [timestamp_ms, value] pairs.
        Timestamps are in milliseconds.
    """
    formatted_series = []
    metric_name_keys = ["task_name", "queue_name"]

    for result in prometheus_response["data"]["result"]:
        data_points = []
        series_name = next(
            (
                result["metric"].get(key)
                for key in metric_name_keys
                if result["metric"].get(key)
            ),
            "sum",
        )

        for value in result["values"]:
            timestamp_ms = float(value[0]) * 1000  # Convert to milliseconds
            metric_value = float(value[1])
            data_points.append([timestamp_ms, metric_value])
        formatted_series.append({"name": series_name, "data": data_points})
    return formatted_series


@router.post("/tasks")
def get_celery_task_metrics(request_body: MetricsRequest) -> list[dict]:
    """Retrieves Celery task metrics from Prometheus based on user input.

    Args:
        request_body: The request body containing parameters for the query.

    Returns:
        A list of dictionaries containing formatted Celery task metrics data.
    """
    prometheus_url_env = os.environ.get("PROMETHEUS_SERVER_URL")
    if not prometheus_url_env:
        return []

    metric_name = request_body.metric_name
    range = request_body.range
    step = request_body.step
    resolution = request_body.resolution
    aggregate = request_body.aggregate

    base_query = f"increase({metric_name}[{resolution}])"
    query = f"sum({base_query})" if aggregate else base_query

    prometheus_response = query_prometheus_range(query, range=range, step=step)
    return format_prometheus_data(prometheus_response)
