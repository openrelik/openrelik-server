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

"""Tests for metrics endpoints."""

from api.v1.metrics import (
    calculate_time_range,
    query_prometheus_range,
    format_prometheus_data,
    get_celery_task_metrics,
)
import pytest
from api.v1.schemas import MetricsRequest
from datetime import datetime, timedelta
import os

PROMETHEUS_SERVER_URL = os.environ.get("PROMETHEUS_SERVER_URL")


def test_calculate_time_range():
    range_seconds = 300  # 5 minutes
    start_time, end_time = calculate_time_range(range_seconds)
    time_diff = end_time - start_time
    assert time_diff == range_seconds


def test_query_prometheus_range(mocker):
    mock_get = mocker.patch("api.v1.metrics.requests.get")
    mock_response = mocker.MagicMock()
    mock_response.json.return_value = {"status": "success", "data": {}}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    query = "test_query"
    range = 300
    step = 60

    result = query_prometheus_range(query, range, step)

    assert result == {"status": "success", "data": {}}
    mock_get.assert_called_once_with(
        f"{PROMETHEUS_SERVER_URL}/api/v1/query_range",
        params={
            "query": query,
            "step": step,
            "start": pytest.approx(
                (datetime.now() - timedelta(seconds=range)).timestamp()
            ),
            "end": pytest.approx(datetime.now().timestamp()),
        },
    )


def test_get_celery_task_metrics(mocker, monkeypatch):
    mock_query_prometheus_range = mocker.patch(
        "api.v1.metrics.query_prometheus_range"
    )
    mock_prometheus_response = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"task_name": "task1"},
                    "values": [[1678886400, "10"], [1678890000, "20"]],
                },
                {
                    "metric": {"queue_name": "queue2"},
                    "values": [[1678886400, "30"], [1678890000, "40"]],
                },
                {
                    "metric": {},
                    "values": [[1678886400, "30"], [1678890000, "40"]],
                },
            ],
        },
    }
    mock_query_prometheus_range.return_value = mock_prometheus_response
    envs = {"PROMETHEUS_SERVER_URL": "http://localhost:9090"}
    monkeypatch.setattr(os, "environ", envs)

    request_body = MetricsRequest(
        metric_name="celery_task_completed_total",
        range=3600,
        step=60,
        resolution="1m",
        aggregate=False,
    )
    expected_data = [
        {"name": "task1", "data": [[1678886400000.0, 10.0], [1678890000000.0, 20.0]]},
        {"name": "queue2", "data": [[1678886400000.0, 30.0], [1678890000000.0, 40.0]]},
        {"name": "sum", "data": [[1678886400000.0, 30.0], [1678890000000.0, 40.0]]},
    ]

    result = get_celery_task_metrics(request_body)

    assert result == expected_data


def test_format_prometheus_data():
    prometheus_response = {
        "data": {
            "result": [
                {
                    "metric": {"task_name": "mytask"},
                    "values": [[1000, "1"], [2000, "2"]],
                }
            ]
        }
    }

    expected_output = [{"name": "mytask", "data": [[1000000.0, 1.0], [2000000.0, 2.0]]}]
    assert format_prometheus_data(prometheus_response) == expected_output


def test_get_celery_task_metrics_no_prometheus(mocker):
    mock_query_prometheus_range = mocker.patch(
        "api.v1.metrics.query_prometheus_range"
    )
    mock_query_prometheus_range.return_value = []
    request_body = MetricsRequest(
        metric_name="celery_task_completed_total",
        range=3600,
        step=60,
        resolution="1m",
        aggregate=False,
    )
    result = get_celery_task_metrics(request_body)
    assert result == []
