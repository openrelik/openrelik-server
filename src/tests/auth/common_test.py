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

"""Tests for auth common functions."""

import json
import pytest
from fastapi import HTTPException
from jose import JWTError

from auth.common import (
    generate_csrf_token,
    create_jwt_token,
    validate_jwt_token,
    verify_csrf,
    get_current_user,
    get_current_active_user,
    authenticated_as_admin,
    refresh,
    csrf,
    logout,
)


def test_generate_csrf_token():
    """Test generate_csrf_token."""
    token = generate_csrf_token()
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_and_validate_jwt_token():
    """Test create_jwt_token and validate_jwt_token."""
    audience = "test-audience"
    expire_minutes = 10
    subject = "test-user"
    token_type = "access"

    # Create token
    token = create_jwt_token(
        audience=audience,
        expire_minutes=expire_minutes,
        subject=subject,
        token_type=token_type,
    )
    assert isinstance(token, str)

    # Validate token
    payload = validate_jwt_token(
        token=token,
        expected_token_type=token_type,
        expected_audience=audience,
    )

    assert payload["sub"] == subject
    assert payload["aud"] == audience
    assert payload["token_type"] == token_type


def test_validate_jwt_token_wrong_type():
    """Test validate_jwt_token with wrong token type."""
    audience = "test-audience"
    token = create_jwt_token(
        audience=audience,
        expire_minutes=10,
        subject="test-user",
        token_type="access",
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_jwt_token(
            token=token,
            expected_token_type="refresh",
            expected_audience=audience,
        )
    assert "Wrong token type" in str(exc_info.value.detail)


def test_validate_jwt_token_jwt_error(mocker):
    """Test validate_jwt_token with JWTError."""
    mocker.patch("auth.common.jwt.decode", side_effect=JWTError("decode error"))
    with pytest.raises(HTTPException) as exc_info:
        validate_jwt_token("token", "access", "aud")
    assert "JWT decode error" in str(exc_info.value.detail)


def test_validate_jwt_token_check_denylist_valid(mocker):
    """Test validate_jwt_token with check_denylist and valid key."""
    audience = "api-client"
    token = create_jwt_token(
        audience=audience,
        expire_minutes=10,
        subject="test-user",
        token_type="access",
    )

    mock_db = mocker.MagicMock()
    mock_api_key = mocker.MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_api_key

    payload = validate_jwt_token(
        token=token,
        expected_token_type="access",
        expected_audience=audience,
        check_denylist=True,
        db=mock_db,
    )
    assert payload["aud"] == audience


def test_validate_jwt_token_check_denylist_invalid(mocker):
    """Test validate_jwt_token with check_denylist and invalid key."""
    audience = "api-client"
    token = create_jwt_token(
        audience=audience,
        expire_minutes=10,
        subject="test-user",
        token_type="access",
    )

    mock_db = mocker.MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        validate_jwt_token(
            token=token,
            expected_token_type="access",
            expected_audience=audience,
            check_denylist=True,
            db=mock_db,
        )
    assert "Invalid API key" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_verify_csrf_browser_get(mocker):
    """Test verify_csrf for GET request from browser."""
    mock_request = mocker.MagicMock()
    mock_request.method = "GET"
    mock_db = mocker.MagicMock()

    mock_validate = mocker.patch("auth.common.validate_jwt_token")
    mock_validate.return_value = {"aud": "browser-client"}

    async for _ in verify_csrf(
        request=mock_request,
        access_token_from_cookie="cookie_token",
        access_token_from_header=None,
        x_csrf_token="csrf",
        csrf_token="csrf",
        db=mock_db,
    ):
        pass


@pytest.mark.asyncio
async def test_verify_csrf_browser_post_invalid(mocker):
    """Test verify_csrf for POST request from browser with invalid csrf."""
    mock_request = mocker.MagicMock()
    mock_request.method = "POST"
    mock_db = mocker.MagicMock()

    mock_validate = mocker.patch("auth.common.validate_jwt_token")
    mock_validate.return_value = {"aud": "browser-client"}

    with pytest.raises(HTTPException) as exc_info:
        async for _ in verify_csrf(
            request=mock_request,
            access_token_from_cookie="cookie_token",
            access_token_from_header=None,
            x_csrf_token="wrong_csrf",
            csrf_token="csrf",
            db=mock_db,
        ):
            pass
    assert exc_info.value.status_code == 400
    assert "X-CSRF-Token is invalid" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_no_token():
    """Test get_current_user with no token."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(None, None, None)
    assert "Token is missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_both_tokens():
    """Test get_current_user with both tokens provided."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user("cookie", "header", None)
    assert "Only one authentication method allowed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_success(mocker):
    """Test get_current_user success."""
    mock_db = mocker.MagicMock()
    mock_validate = mocker.patch("auth.common.validate_jwt_token")
    mock_validate.return_value = {"sub": "user_uuid"}

    mock_get_user = mocker.patch("auth.common.get_user_by_uuid_from_db")
    mock_user = mocker.MagicMock()
    mock_get_user.return_value = mock_user

    user = await get_current_user("cookie", None, mock_db)
    assert user == mock_user


@pytest.mark.asyncio
async def test_get_current_user_not_found(mocker):
    """Test get_current_user when user is not found."""
    mock_db = mocker.MagicMock()
    mock_validate = mocker.patch("auth.common.validate_jwt_token")
    mock_validate.return_value = {"sub": "user_uuid"}

    mock_get_user = mocker.patch("auth.common.get_user_by_uuid_from_db")
    mock_get_user.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user("cookie", None, mock_db)
    assert "No such user" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_active_user_active(mocker):
    """Test get_current_active_user with active user."""
    mock_user = mocker.MagicMock()
    mock_user.is_active = True
    user = await get_current_active_user(mock_user)
    assert user == mock_user


@pytest.mark.asyncio
async def test_get_current_active_user_inactive(mocker):
    """Test get_current_active_user with inactive user."""
    mock_user = mocker.MagicMock()
    mock_user.is_active = False
    with pytest.raises(HTTPException) as exc_info:
        await get_current_active_user(mock_user)
    assert exc_info.value.status_code == 400
    assert "Inactive user" in exc_info.value.detail


def test_authenticated_as_admin_true(mocker):
    """Test authenticated_as_admin with admin user."""
    mock_user = mocker.MagicMock()
    mock_user.is_admin = True
    user = authenticated_as_admin(mock_user)
    assert user == mock_user


def test_authenticated_as_admin_false(mocker):
    """Test authenticated_as_admin with non-admin user."""
    mock_user = mocker.MagicMock()
    mock_user.is_admin = False
    with pytest.raises(HTTPException) as exc_info:
        authenticated_as_admin(mock_user)
    assert exc_info.value.status_code == 403
    assert "User is not an admin" in exc_info.value.detail


@pytest.mark.asyncio
async def test_refresh_no_token():
    """Test refresh with no token."""
    with pytest.raises(HTTPException) as exc_info:
        await refresh(None, None, None)
    assert "Token is missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_refresh_cookie(mocker):
    """Test refresh with cookie token."""
    mocker.patch(
        "auth.common.config",
        {"auth": {"jwt_cookie_access_expire_minutes": 15}},
    )
    mock_db = mocker.MagicMock()
    mock_validate = mocker.patch("auth.common.validate_jwt_token")
    mock_validate.return_value = {"aud": "browser-client", "sub": "user_uuid"}

    mock_create = mocker.patch("auth.common.create_jwt_token")
    mock_create.return_value = "new_access_token"

    mock_generate = mocker.patch("auth.common.generate_csrf_token")
    mock_generate.return_value = "new_csrf_token"

    response = await refresh("cookie_token", None, mock_db)
    assert response.status_code == 200
    data = json.loads(response.body)
    assert data["new_access_token"] == "new_access_token"
    assert data["new_csrf_token"] == "new_csrf_token"


@pytest.mark.asyncio
async def test_refresh_header(mocker):
    """Test refresh with header token."""
    mocker.patch(
        "auth.common.config",
        {"auth": {"jwt_header_default_access_expire_minutes": 15}},
    )
    mock_db = mocker.MagicMock()
    mock_validate = mocker.patch("auth.common.validate_jwt_token")
    mock_validate.return_value = {"aud": "api-client", "sub": "user_uuid"}

    mock_create = mocker.patch("auth.common.create_jwt_token")
    mock_create.return_value = "new_access_token"

    mock_generate = mocker.patch("auth.common.generate_csrf_token")
    mock_generate.return_value = "new_csrf_token"

    response = await refresh(None, "header_token", mock_db)
    assert response.status_code == 200
    data = json.loads(response.body)
    assert data["new_access_token"] == "new_access_token"
    assert data["new_csrf_token"] == "new_csrf_token"


@pytest.mark.asyncio
async def test_csrf(mocker):
    """Test csrf endpoint."""
    mock_user = mocker.MagicMock()
    token = await csrf("cookie_token", mock_user)
    assert token == "cookie_token"


@pytest.mark.asyncio
async def test_logout(mocker):
    """Test logout endpoint."""
    mock_response = mocker.MagicMock()
    result = await logout(mock_response)
    assert result == {"message": "Logged out"}
    mock_response.delete_cookie.assert_any_call(key="refresh_token")
    mock_response.delete_cookie.assert_any_call(key="access_token")
    mock_response.delete_cookie.assert_any_call(key="csrf_token")
