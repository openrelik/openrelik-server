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

"""Tests the configs endpoints."""


def test_get_system_config(fastapi_test_client, mocker):
    """Test the get_system_config endpoint."""
    mock_get_active_llms = mocker.patch("api.v1.configs.get_active_llms")

    mock_active_llms = [{"name": "test_llm"}]
    mock_get_active_llms.return_value = mock_active_llms

    response = fastapi_test_client.get("/configs/system/")
    assert response.status_code == 200
    assert response.json()["active_llms"] == mock_active_llms
    assert response.json()["allowed_data_types_preview"] == [
        "openrelik:hayabusa:html_report"
    ]
