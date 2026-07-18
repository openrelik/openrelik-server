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

try:
    from config import config

    if "auth" not in config:
        config["auth"] = {}
    config["auth"]["iap"] = {
        "audience": "/projects/123/global/backendServices/456",
        "allowlist": [],
        "public_access": False,
    }
    config["auth"]["jwt_cookie_refresh_expire_minutes"] = 60
    config["auth"]["jwt_cookie_access_expire_minutes"] = 15
except ImportError:
    pass

import auth.iap as iap_auth


def test_validate_user_info_public_access(mocker):
    """Test public access allowed."""
    mocker.patch("auth.iap.IAP_PUBLIC_ACCESS", True)
    mocker.patch("auth.iap.IAP_ALLOW_LIST", [])
    user_info = {"email": "user@any.com"}
    # Should not raise any exception
    iap_auth._validate_user_info(user_info)


def test_validate_user_info_allowlist_ok(mocker):
    """Test user in allowlist."""
    mocker.patch("auth.iap.IAP_PUBLIC_ACCESS", False)
    mocker.patch("auth.iap.IAP_ALLOW_LIST", ["user@allowed.com"])
    user_info = {"email": "user@allowed.com"}
    # Should not raise any exception
    iap_auth._validate_user_info(user_info)


def test_validate_user_info_allowlist_fail(mocker):
    """Test user not in allowlist."""
    mocker.patch("auth.iap.IAP_PUBLIC_ACCESS", False)
    mocker.patch("auth.iap.IAP_ALLOW_LIST", ["user@allowed.com"])
    user_info = {"email": "user@notallowed.com"}
    with pytest.raises(HTTPException) as excinfo:
        iap_auth._validate_user_info(user_info)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Unauthorized. Not in allowlist."


def test_validate_iap_assertion_success(mocker):
    """Test assertion validation with valid claims."""
    mock_verify_token = mocker.patch("auth.iap.id_token.verify_token")
    mock_verify_token.return_value = {
        "iss": "https://cloud.google.com/iap",
        "email": "user@example.com",
    }

    claims = iap_auth._validate_iap_assertion("valid-assertion")

    assert claims["email"] == "user@example.com"
    mock_verify_token.assert_called_once()
    _, kwargs = mock_verify_token.call_args
    assert kwargs["audience"] == iap_auth.IAP_AUDIENCE
    assert kwargs["certs_url"] == iap_auth.IAP_CERTS_URL


def test_validate_iap_assertion_invalid_token(mocker):
    """Test assertion validation with an invalid signature/audience/expiry."""
    mock_verify_token = mocker.patch("auth.iap.id_token.verify_token")
    mock_verify_token.side_effect = ValueError("invalid token")

    with pytest.raises(HTTPException) as excinfo:
        iap_auth._validate_iap_assertion("invalid-assertion")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Unauthorized. Invalid IAP assertion."


def test_validate_iap_assertion_pyjwt_error(mocker):
    """Test assertion validation when PyJWT raises (malformed token, bad audience)."""
    from jwt.exceptions import InvalidAudienceError

    mock_verify_token = mocker.patch("auth.iap.id_token.verify_token")
    mock_verify_token.side_effect = InvalidAudienceError("Audience doesn't match")

    with pytest.raises(HTTPException) as excinfo:
        iap_auth._validate_iap_assertion("assertion-with-wrong-audience")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Unauthorized. Invalid IAP assertion."


def test_validate_iap_assertion_wrong_issuer(mocker):
    """Test assertion validation with an unexpected issuer."""
    mock_verify_token = mocker.patch("auth.iap.id_token.verify_token")
    mock_verify_token.return_value = {
        "iss": "https://accounts.google.com",
        "email": "user@example.com",
    }

    with pytest.raises(HTTPException) as excinfo:
        iap_auth._validate_iap_assertion("assertion-with-wrong-issuer")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Unauthorized. Invalid issuer."


@pytest.mark.asyncio
async def test_login_missing_header(mocker):
    """Test login without an assertion header."""
    mock_db = mocker.MagicMock()

    with pytest.raises(HTTPException) as excinfo:
        await iap_auth.login(x_goog_iap_jwt_assertion=None, db=mock_db)

    assert excinfo.value.status_code == 401
    assert "Missing X-Goog-IAP-JWT-Assertion" in excinfo.value.detail


@pytest.mark.asyncio
async def test_login_missing_email_claim(mocker):
    """Test login with an assertion that has no email claim."""
    mock_validate_assertion = mocker.patch("auth.iap._validate_iap_assertion")
    mock_validate_assertion.return_value = {"iss": "https://cloud.google.com/iap"}
    mock_db = mocker.MagicMock()

    with pytest.raises(HTTPException) as excinfo:
        await iap_auth.login(x_goog_iap_jwt_assertion="assertion", db=mock_db)

    assert excinfo.value.status_code == 401
    assert "no email claim" in excinfo.value.detail


@pytest.mark.asyncio
async def test_login_success(mocker):
    """Test login success with existing user."""
    mock_validate_assertion = mocker.patch("auth.iap._validate_iap_assertion")
    mock_get_user = mocker.patch("auth.iap.get_user_by_email_from_db")
    mock_validate_user_info = mocker.patch("auth.iap._validate_user_info")
    mock_create_jwt = mocker.patch("auth.iap.create_jwt_token")
    mock_generate_csrf = mocker.patch("auth.iap.generate_csrf_token")

    mock_validate_assertion.return_value = {"email": "user@example.com"}
    mock_user = mocker.MagicMock()
    mock_user.uuid.hex = "user_uuid"
    mock_get_user.return_value = mock_user
    mock_create_jwt.return_value = "mocked_jwt"
    mock_generate_csrf.return_value = "mocked_csrf"

    mock_db = mocker.MagicMock()

    response = await iap_auth.login(x_goog_iap_jwt_assertion="assertion", db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 307
    mock_validate_user_info.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, email="user@example.com")


@pytest.mark.asyncio
async def test_login_new_user(mocker):
    """Test login with new user."""
    mock_validate_assertion = mocker.patch("auth.iap._validate_iap_assertion")
    mock_get_user = mocker.patch("auth.iap.get_user_by_email_from_db")
    _ = mocker.patch(
        "auth.iap._validate_user_info"
    )  # Needed to bypass list of allowed users
    mock_create_user = mocker.patch("auth.iap.create_user_in_db")
    mock_create_jwt = mocker.patch("auth.iap.create_jwt_token")
    mock_generate_csrf = mocker.patch("auth.iap.generate_csrf_token")

    mock_validate_assertion.return_value = {"email": "new@example.com"}
    mock_get_user.return_value = None
    mock_user = mocker.MagicMock()
    mock_user.uuid.hex = "new_uuid"
    mock_create_user.return_value = mock_user
    mock_create_jwt.return_value = "mocked_jwt"
    mock_generate_csrf.return_value = "mocked_csrf"

    mock_db = mocker.MagicMock()

    response = await iap_auth.login(x_goog_iap_jwt_assertion="assertion", db=mock_db)

    assert isinstance(response, RedirectResponse)
    mock_create_user.assert_called_once()
    # The new user record is provisioned from the verified email claim.
    _, kwargs = mock_create_user.call_args
    new_user = kwargs.get("new_user") or mock_create_user.call_args[0][1]
    assert new_user.email == "new@example.com"
    assert new_user.auth_method == "iap"


@pytest.mark.asyncio
async def test_login_not_in_allowlist(mocker):
    """Test login with a user that is not authorized."""
    mock_validate_assertion = mocker.patch("auth.iap._validate_iap_assertion")
    mock_validate_assertion.return_value = {"email": "user@notallowed.com"}
    mocker.patch("auth.iap.IAP_PUBLIC_ACCESS", False)
    mocker.patch("auth.iap.IAP_ALLOW_LIST", ["user@allowed.com"])

    mock_db = mocker.MagicMock()

    with pytest.raises(HTTPException) as excinfo:
        await iap_auth.login(x_goog_iap_jwt_assertion="assertion", db=mock_db)

    assert excinfo.value.status_code == 401
