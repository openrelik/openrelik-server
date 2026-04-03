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

import pytest
from auth.common import (
    generate_csrf_token,
    create_jwt_token,
    validate_jwt_token,
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
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        validate_jwt_token(
            token=token,
            expected_token_type="refresh",
            expected_audience=audience,
        )
    assert "Wrong token type" in str(exc_info.value.detail)
