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
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuthError

try:
    from config import config

    config["auth"] = {
        "oidc": {
            "client_id": "test_id",
            "client_secret": "test_secret",
            "discovery_url": "https://test.discovery.url",
            "allowlist": [],
            "public_access": False,
            "redirect_uri": None,
        },
        "jwt_cookie_refresh_expire_minutes": 60,
        "jwt_cookie_access_expire_minutes": 15,
    }
except ImportError:
    pass

import auth.oidc as oidc_auth


def test_validate_user_info_public_access(mocker):
    """Test public access allowed."""
    mocker.patch("auth.oidc.OIDC_PUBLIC_ACCESS", True)
    mocker.patch("auth.oidc.OIDC_ALLOW_LIST", [])
    user_info = {"email": "user@any.com"}
    # Should not raise any exception
    oidc_auth._validate_user_info(user_info)


def test_validate_user_info_allowlist_ok(mocker):
    """Test user in allowlist."""
    mocker.patch("auth.oidc.OIDC_PUBLIC_ACCESS", False)
    mocker.patch("auth.oidc.OIDC_ALLOW_LIST", ["user@allowed.com"])
    user_info = {"email": "user@allowed.com"}
    # Should not raise any exception
    oidc_auth._validate_user_info(user_info)


def test_validate_user_info_allowlist_fail(mocker):
    """Test user not in allowlist."""
    mocker.patch("auth.oidc.OIDC_PUBLIC_ACCESS", False)
    mocker.patch("auth.oidc.OIDC_ALLOW_LIST", ["user@allowed.com"])
    user_info = {"email": "user@notallowed.com"}
    with pytest.raises(HTTPException) as excinfo:
        oidc_auth._validate_user_info(user_info)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Unauthorized. Not in allowlist."


@pytest.mark.asyncio
async def test_login(mocker):
    """Test login endpoint redirects to OIDC."""
    mock_authorize_redirect = mocker.patch("auth.oidc.oauth.oidc.authorize_redirect")
    mock_request = mocker.MagicMock()
    mock_request.url_for.return_value = "http://test/auth/oidc"
    mock_authorize_redirect.return_value = "mock_redirect"

    mocker.patch("auth.oidc.OIDC_REDIRECT_URI", None)

    response = await oidc_auth.login(mock_request)

    assert response == "mock_redirect"
    mock_authorize_redirect.assert_called_once_with(
        mock_request, "http://test/auth/oidc"
    )


@pytest.mark.asyncio
async def test_login_with_redirect_uri(mocker):
    """Test login endpoint uses OIDC_REDIRECT_URI if set."""
    mock_authorize_redirect = mocker.patch("auth.oidc.oauth.oidc.authorize_redirect")
    mock_request = mocker.MagicMock()
    mock_authorize_redirect.return_value = "mock_redirect"

    mocker.patch("auth.oidc.OIDC_REDIRECT_URI", "http://custom/redirect")

    response = await oidc_auth.login(mock_request)

    assert response == "mock_redirect"
    mock_authorize_redirect.assert_called_once_with(
        mock_request, "http://custom/redirect"
    )


@pytest.mark.asyncio
async def test_oidc_auth_success(mocker):
    """Test auth callback success with existing user."""
    mock_authorize_access_token = mocker.patch(
        "auth.oidc.oauth.oidc.authorize_access_token"
    )
    mock_get_user = mocker.patch("auth.oidc.get_user_by_email_from_db")
    mock_validate_user_info = mocker.patch("auth.oidc._validate_user_info")
    mock_create_jwt = mocker.patch("auth.oidc.create_jwt_token")
    mock_generate_csrf = mocker.patch("auth.oidc.generate_csrf_token")

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

    response = await oidc_auth.oidc_auth(mock_request, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 307
    mock_validate_user_info.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, email="user@example.com")


@pytest.mark.asyncio
async def test_oidc_auth_new_user(mocker):
    """Test auth callback with new user."""
    mock_authorize_access_token = mocker.patch(
        "auth.oidc.oauth.oidc.authorize_access_token"
    )
    mock_get_user = mocker.patch("auth.oidc.get_user_by_email_from_db")
    _ = mocker.patch(
        "auth.oidc._validate_user_info"
    )  # Needed to bypass list of allowed users
    mock_create_user = mocker.patch("auth.oidc.create_user_in_db")
    mock_create_jwt = mocker.patch("auth.oidc.create_jwt_token")
    mock_generate_csrf = mocker.patch("auth.oidc.generate_csrf_token")

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

    response = await oidc_auth.oidc_auth(mock_request, db=mock_db)

    assert isinstance(response, RedirectResponse)
    mock_create_user.assert_called_once()


@pytest.mark.asyncio
async def test_oidc_auth_oauth_error(mocker):
    """Test auth callback with OAuth error."""
    mock_authorize_access_token = mocker.patch(
        "auth.oidc.oauth.oidc.authorize_access_token"
    )
    mock_authorize_access_token.side_effect = OAuthError(error="invalid_grant")

    mock_request = mocker.MagicMock()
    mock_db = mocker.MagicMock()

    with pytest.raises(HTTPException) as excinfo:
        await oidc_auth.oidc_auth(mock_request, db=mock_db)

    assert excinfo.value.status_code == 401
    assert "OAuth error: invalid_grant" in excinfo.value.detail


@pytest.mark.asyncio
async def test_oidc_auth_missing_userinfo(mocker):
    """Test auth callback missing userinfo."""
    mock_authorize_access_token = mocker.patch(
        "auth.oidc.oauth.oidc.authorize_access_token"
    )
    mock_authorize_access_token.return_value = {}  # missing userinfo

    mock_request = mocker.MagicMock()
    mock_db = mocker.MagicMock()

    with pytest.raises(HTTPException) as excinfo:
        await oidc_auth.oidc_auth(mock_request, db=mock_db)

    assert excinfo.value.status_code == 401
    assert "Could not retrieve user info" in excinfo.value.detail
