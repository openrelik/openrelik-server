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

import pytest
from fastapi import HTTPException
from google.auth import exceptions as google_exceptions
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuthError

# Mock config before importing google
try:
    from config import config

    config["auth"] = {
        "google": {
            "client_id": "test_id",
            "client_secret": "test_secret",
            "allowlist": [],
            "public_access": False,
            "workspace_domain": False,
            "allowed_robot_accounts": [],
            "extra_audiences": [],
        },
        "jwt_cookie_refresh_expire_minutes": 60,
        "jwt_cookie_access_expire_minutes": 15,
    }
except:
    pass

import auth.google as google_auth


def test_validate_user_info_robot():
    """Test allowed robot accounts bypass checks."""
    google_auth.GOOGLE_ALLOWED_ROBOT_ACCOUNTS = ["robot@example.com"]
    user_info = {"email": "robot@example.com"}
    # Should not raise any exception
    google_auth._validate_user_info(user_info)


def test_validate_user_info_workspace_ok():
    """Test valid workspace domain."""
    google_auth.GOOGLE_WORKSPACE_DOMAIN = "example.com"
    google_auth.GOOGLE_PUBLIC_ACCESS = True
    google_auth.GOOGLE_ALLOWED_ROBOT_ACCOUNTS = []
    user_info = {"email": "user@example.com", "hd": "example.com"}
    # Should not raise any exception
    google_auth._validate_user_info(user_info)


def test_validate_user_info_workspace_fail():
    """Test invalid workspace domain."""
    google_auth.GOOGLE_WORKSPACE_DOMAIN = "example.com"
    google_auth.GOOGLE_ALLOWED_ROBOT_ACCOUNTS = []
    user_info = {"email": "user@gmail.com", "hd": "gmail.com"}
    with pytest.raises(HTTPException) as excinfo:
        google_auth._validate_user_info(user_info)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Unauthorized. Invalid workspace domain."


def test_validate_user_info_public_access():
    """Test public access allowed."""
    google_auth.GOOGLE_WORKSPACE_DOMAIN = False
    google_auth.GOOGLE_PUBLIC_ACCESS = True
    google_auth.GOOGLE_ALLOWED_ROBOT_ACCOUNTS = []
    user_info = {"email": "user@any.com"}
    # Should not raise any exception
    google_auth._validate_user_info(user_info)


def test_validate_user_info_allowlist_ok():
    """Test user in allowlist."""
    google_auth.GOOGLE_WORKSPACE_DOMAIN = False
    google_auth.GOOGLE_PUBLIC_ACCESS = False
    google_auth.GOOGLE_ALLOW_LIST = ["user@allowed.com"]
    google_auth.GOOGLE_ALLOWED_ROBOT_ACCOUNTS = []
    user_info = {"email": "user@allowed.com"}
    # Should not raise any exception
    google_auth._validate_user_info(user_info)


def test_validate_user_info_allowlist_fail():
    """Test user not in allowlist."""
    google_auth.GOOGLE_WORKSPACE_DOMAIN = False
    google_auth.GOOGLE_PUBLIC_ACCESS = False
    google_auth.GOOGLE_ALLOW_LIST = ["user@allowed.com"]
    google_auth.GOOGLE_ALLOWED_ROBOT_ACCOUNTS = []
    user_info = {"email": "user@notallowed.com"}
    with pytest.raises(HTTPException) as excinfo:
        google_auth._validate_user_info(user_info)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Unauthorized. Not in allowlist."


@pytest.mark.asyncio
async def test_auth_header_token_missing_header(mocker):
    """Test auth_header_token with missing header."""
    with pytest.raises(HTTPException) as excinfo:
        await google_auth.auth_header_token(x_goog_id_token=None, db=mocker.MagicMock())
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Unauthorized, missing x-google-id-token header."


@pytest.mark.asyncio
async def test_auth_header_token_valid_new_user(mocker):
    """Test auth_header_token with valid token and new user."""
    mock_validate_google_token = mocker.patch("auth.google._validate_google_token")
    mock_get_user = mocker.patch("auth.google.get_user_by_email_from_db")
    mock_validate_user_info = mocker.patch("auth.google._validate_user_info")
    mock_create_jwt = mocker.patch("auth.google.create_jwt_token")

    mock_validate_google_token.return_value = {
        "email": "new@example.com",
        "name": "New User",
        "picture": "http://pic",
    }
    mock_get_user.return_value = None
    mock_create_jwt.return_value = "mocked_jwt"

    mock_db = mocker.MagicMock()

    response = await google_auth.auth_header_token(
        x_goog_id_token="valid_token", db=mock_db
    )

    assert response["x-openrelik-refresh-token"] == "mocked_jwt"
    assert response["x-openrelik-access-token"] == "mocked_jwt"
    mock_validate_user_info.assert_called_once()


@pytest.mark.asyncio
async def test_auth_header_token_valid_existing_user(mocker):
    """Test auth_header_token with valid token and existing user."""
    mock_validate_google_token = mocker.patch("auth.google._validate_google_token")
    mock_get_user = mocker.patch("auth.google.get_user_by_email_from_db")
    mock_validate_user_info = mocker.patch("auth.google._validate_user_info")
    mock_create_jwt = mocker.patch("auth.google.create_jwt_token")

    mock_validate_google_token.return_value = {
        "email": "existing@example.com",
        "name": "Existing User",
        "picture": "http://pic",
    }
    mock_user = mocker.MagicMock()
    mock_user.uuid.hex = "existing_uuid"
    mock_get_user.return_value = mock_user
    mock_create_jwt.return_value = "mocked_jwt"

    mock_db = mocker.MagicMock()

    response = await google_auth.auth_header_token(
        x_goog_id_token="valid_token", db=mock_db
    )

    assert response["x-openrelik-refresh-token"] == "mocked_jwt"
    assert response["x-openrelik-access-token"] == "mocked_jwt"
    mock_validate_user_info.assert_called_once()


def test_validate_google_token_success(mocker):
    """Test _validate_google_token success."""
    mock_verify = mocker.patch("auth.google.id_token.verify_oauth2_token")
    mock_verify.return_value = {"aud": "test_aud", "email": "user@example.com"}
    result = google_auth._validate_google_token("valid_token", ["test_aud"])
    assert result["email"] == "user@example.com"


def test_validate_google_token_aud_mismatch(mocker):
    """Test _validate_google_token audience mismatch."""
    mock_verify = mocker.patch("auth.google.id_token.verify_oauth2_token")
    mock_verify.return_value = {"aud": "wrong_aud"}
    with pytest.raises(HTTPException) as excinfo:
        google_auth._validate_google_token("valid_token", ["test_aud"])
    assert excinfo.value.status_code == 401
    assert "Could not verify audience" in excinfo.value.detail


def test_validate_google_token_value_error(mocker):
    """Test _validate_google_token value error."""
    mock_verify = mocker.patch("auth.google.id_token.verify_oauth2_token")
    mock_verify.side_effect = ValueError("Invalid token")
    with pytest.raises(HTTPException) as excinfo:
        google_auth._validate_google_token("invalid_token", ["test_aud"])
    assert excinfo.value.status_code == 401
    assert "Invalid token" in excinfo.value.detail


def test_validate_google_token_auth_error(mocker):
    """Test _validate_google_token auth error."""
    mock_verify = mocker.patch("auth.google.id_token.verify_oauth2_token")
    mock_verify.side_effect = google_exceptions.GoogleAuthError("Auth error")
    with pytest.raises(HTTPException) as excinfo:
        google_auth._validate_google_token("invalid_token", ["test_aud"])
    assert excinfo.value.status_code == 401
    assert "Could not verify token" in excinfo.value.detail


@pytest.mark.asyncio
async def test_login(mocker):
    """Test login endpoint redirects to Google."""
    mock_authorize_redirect = mocker.patch(
        "auth.google.oauth.google.authorize_redirect"
    )
    mock_request = mocker.MagicMock()
    mock_request.url_for.return_value = "http://test/auth"
    mock_authorize_redirect.return_value = "mock_redirect"

    google_auth.GOOGLE_WORKSPACE_DOMAIN = "example.com"

    response = await google_auth.login(mock_request)

    assert response == "mock_redirect"
    mock_authorize_redirect.assert_called_once_with(
        mock_request, "http://test/auth", hd="example.com"
    )


@pytest.mark.asyncio
async def test_auth_callback(mocker):
    """Test auth callback success."""
    mock_authorize_access_token = mocker.patch(
        "auth.google.oauth.google.authorize_access_token"
    )
    mock_get_user = mocker.patch("auth.google.get_user_by_email_from_db")
    mock_validate_user_info = mocker.patch("auth.google._validate_user_info")
    mock_create_jwt = mocker.patch("auth.google.create_jwt_token")
    mock_generate_csrf = mocker.patch("auth.google.generate_csrf_token")

    mock_authorize_access_token.return_value = {
        "userinfo": {
            "email": "user@example.com",
            "name": "User",
            "picture": "http://pic",
        }
    }
    mock_user = mocker.MagicMock()
    mock_user.uuid.hex = "user_uuid"
    mock_get_user.return_value = mock_user
    mock_create_jwt.return_value = "mocked_jwt"
    mock_generate_csrf.return_value = "mocked_csrf"

    mock_request = mocker.MagicMock()
    mock_db = mocker.MagicMock()

    response = await google_auth.auth(mock_request, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 307


@pytest.mark.asyncio
async def test_auth_callback_oauth_error(mocker):
    """Test auth callback with OAuth error."""
    mock_authorize_access_token = mocker.patch(
        "auth.google.oauth.google.authorize_access_token"
    )
    mock_authorize_access_token.side_effect = OAuthError(error="invalid_grant")

    mock_request = mocker.MagicMock()
    mock_db = mocker.MagicMock()

    response = await google_auth.auth(mock_request, db=mock_db)

    assert response == {"OAuth error": "invalid_grant"}


@pytest.mark.asyncio
async def test_auth_callback_new_user(mocker):
    """Test auth callback with new user."""
    mock_authorize_access_token = mocker.patch(
        "auth.google.oauth.google.authorize_access_token"
    )
    mock_get_user = mocker.patch("auth.google.get_user_by_email_from_db")
    mock_validate_user_info = mocker.patch("auth.google._validate_user_info")
    mock_create_user = mocker.patch("auth.google.create_user_in_db")
    mock_create_jwt = mocker.patch("auth.google.create_jwt_token")
    mock_generate_csrf = mocker.patch("auth.google.generate_csrf_token")

    mock_authorize_access_token.return_value = {
        "userinfo": {
            "email": "new@example.com",
            "name": "New User",
            "picture": "http://pic",
        }
    }
    mock_get_user.return_value = None
    mock_user = mocker.MagicMock()
    mock_user.uuid.hex = "new_uuid"
    mock_create_user.return_value = mock_user
    mock_create_jwt.return_value = "mocked_jwt"
    mock_generate_csrf.return_value = "mocked_csrf"

    mock_request = mocker.MagicMock()
    mock_db = mocker.MagicMock()

    response = await google_auth.auth(mock_request, db=mock_db)

    assert isinstance(response, RedirectResponse)
    mock_create_user.assert_called_once()
