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

"""Tests for local auth endpoint."""

import pytest
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from auth.local import auth_local


@pytest.mark.asyncio
async def test_auth_local_success(mocker, db):
    """Test auth_local success."""
    # Setup mocks
    mock_generate_csrf = mocker.patch("auth.local.generate_csrf_token")
    mock_create_jwt = mocker.patch("auth.local.create_jwt_token")
    mock_hasher = mocker.patch("auth.local.password_hasher")
    mock_get_user = mocker.patch("auth.local.get_user_by_username_from_db")

    mock_user = mocker.MagicMock()
    mock_user.password_hash = "correct_hash"
    mock_user.uuid.hex = "mock_uuid"
    mock_get_user.return_value = mock_user

    mock_hasher.verify.return_value = True
    mock_create_jwt.return_value = "mock_token"
    mock_generate_csrf.return_value = "mock_csrf"

    # Mock form data
    form_data = OAuth2PasswordRequestForm(username="testuser", password="password")

    # Mock request
    request = mocker.MagicMock()

    # Call function
    response = await auth_local(request, form_data, db)

    # Assertions
    mock_get_user.assert_called_once_with(db, username="testuser")
    mock_hasher.verify.assert_called_once_with("correct_hash", "password")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_local_wrong_password(mocker, db):
    """Test auth_local with wrong password."""
    import argon2

    # Setup mocks
    mock_hasher = mocker.patch("auth.local.password_hasher")
    mock_get_user = mocker.patch("auth.local.get_user_by_username_from_db")

    mock_user = mocker.MagicMock()
    mock_user.password_hash = "correct_hash"
    mock_get_user.return_value = mock_user

    mock_hasher.verify.side_effect = argon2.exceptions.VerifyMismatchError

    # Mock form data
    form_data = OAuth2PasswordRequestForm(
        username="testuser", password="wrong_password"
    )

    # Mock request
    request = mocker.MagicMock()

    # Call function and assert exception
    with pytest.raises(HTTPException) as exc_info:
        await auth_local(request, form_data, db)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Incorrect username or password" in exc_info.value.detail


@pytest.mark.asyncio
async def test_auth_local_user_not_found(mocker, db):
    """Test auth_local with user not found."""
    # Setup mocks
    mock_get_user = mocker.patch("auth.local.get_user_by_username_from_db")
    mock_get_user.return_value = None

    # Mock form data
    form_data = OAuth2PasswordRequestForm(username="nonexistent", password="password")

    # Mock request
    request = mocker.MagicMock()

    # Call function and assert exception
    with pytest.raises(HTTPException) as exc_info:
        await auth_local(request, form_data, db)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Incorrect username or password" in exc_info.value.detail
