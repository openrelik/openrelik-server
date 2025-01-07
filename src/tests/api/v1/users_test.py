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

"""Tests for users endpoints."""

import pytest
from api.v1.schemas import UserSearchResponse


def test_get_current_user(fastapi_test_client, user_response):
    """Test the get_current_user endpoint."""
    response = fastapi_test_client.get("/users/me/")
    assert response.status_code == 200
    assert response.json() == user_response.model_dump(mode="json")


search_user_response = UserSearchResponse(
        display_name="Test User",
        username="test_user",
        profile_picture_url="http://localhost/profile/pic",
        id=1,
        created_at = "2025-01-07T18:29:07.772000Z",
        updated_at = "2025-01-07T18:29:07.772000Z",
        deleted_at = None,
        is_deleted = False
    ).model_dump(mode="json")

@pytest.mark.parametrize(
    "search_string, expected_response",
    [
        ("test_user", [search_user_response]),
        ("", []),
        ("test", [])
    ],
)
def test_search_users_with_query(
    fastapi_test_client, mocker, search_string, expected_response
):
    """Test the search_users_with_query endpoint."""
    mock_search_users = mocker.patch("api.v1.users.search_users")
    mock_search_users.return_value = expected_response
    response = fastapi_test_client.post("/users/search", json={"search_string": search_string})
    assert response.status_code == 200
    assert response.json() == expected_response


def test_get_api_key_for_current_user(fastapi_test_client, mocker, user_api_key_response):
    """Test the get_api_key_for_current_user endpoint."""
    mock_get_user_api_keys_from_db = mocker.patch(
        "api.v1.users.get_user_api_keys_from_db"
    )
    mock_get_user_api_keys_from_db.return_value = user_api_key_response
    response = fastapi_test_client.get("/users/me/apikeys/")
    mock_get_user_api_keys_from_db.assert_called_once()
    assert response.status_code == 200
    assert response.json() == user_api_key_response


def test_create_api_key_for_current_user(fastapi_test_client, mocker, regular_user):
    """Test the create_api_key_for_current_user endpoint."""
    mock_jwt_token = "mock_jwt_token"
    mock_jwt_payload = {
        "jti": "somejti",
        "exp": 1234567890,
        "sub": regular_user.uuid.hex,
        "token_use": "access",
        "scope": "",
        "aud": ["api-client"],
        "iat": 1234567885,
        "nbf": 1234567885,
    }
    mock_create_jwt_token = mocker.patch("api.v1.users.create_jwt_token")
    mock_create_jwt_token.return_value = mock_jwt_token
    mock_validate_jwt_token = mocker.patch("api.v1.users.validate_jwt_token")
    mock_validate_jwt_token.return_value = mock_jwt_payload
    mock_create_user_api_key_in_db = mocker.patch(
        "api.v1.users.create_user_api_key_in_db"
    )
    mock_create_user_api_key_in_db.return_value = None
    mock_config = mocker.patch("config.get_config")
    mock_config.return_value = {"auth": {"jwt_header_default_refresh_expire_minutes": 120}}
    request_body = {
        "display_name": "new_api_key",
        "description": "new key description",
    }
    response = fastapi_test_client.post("/users/me/apikeys/", json=request_body)
    mock_create_user_api_key_in_db.assert_called_once()
    assert response.status_code == 200
    assert response.json() == {"token": mock_jwt_token, "display_name": "new_api_key"}


def test_delete_api_key(fastapi_test_client, mocker):
    """Test the delete_api_key endpoint."""
    mock_delete_user_api_key_from_db = mocker.patch(
        "api.v1.users.delete_user_api_key_from_db"
    )
    mock_delete_user_api_key_from_db.return_value = None
    response = fastapi_test_client.delete("/users/me/apikeys/1")
    assert response.status_code == 200
    mock_delete_user_api_key_from_db.assert_called_once()

