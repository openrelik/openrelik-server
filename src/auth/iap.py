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
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from google.auth.transport import requests
from google.oauth2 import id_token
from jwt.exceptions import PyJWTError
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from api.v1 import schemas
from config import config
from datastores.sql.crud.user import create_user_in_db, get_user_by_email_from_db
from datastores.sql.database import get_db_connection

from .common import UI_SERVER_URL, create_jwt_token, generate_csrf_token

router = APIRouter()

# Issuer and signing keys for IAP assertions, see
# https://cloud.google.com/iap/docs/signed-headers-howto
IAP_ISSUER = "https://cloud.google.com/iap"
DEFAULT_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key-jwk"

IAP_AUDIENCE = config["auth"]["iap"]["audience"]
IAP_CERTS_URL = config["auth"]["iap"].get("certs_url") or DEFAULT_CERTS_URL
IAP_ALLOW_LIST = config["auth"]["iap"].get("allowlist", [])
IAP_PUBLIC_ACCESS = config["auth"]["iap"].get("public_access", False)
REFRESH_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_cookie_refresh_expire_minutes"]
ACCESS_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_cookie_access_expire_minutes"]


def _validate_iap_assertion(assertion: str) -> dict[str, Any]:
    """Validates a Google Cloud IAP signed-header assertion.

    Verifies the JWT signature against IAP's public keys, and checks the
    expiry, audience and issuer claims. The raw header value must never be
    trusted without this verification.

    Args:
        assertion (str): The JWT from the X-Goog-IAP-JWT-Assertion header.

    Returns:
        dict: The verified claims.

    Raises:
        HTTPException: If the assertion is invalid.
    """
    try:
        claims = id_token.verify_token(
            assertion,
            requests.Request(),
            audience=IAP_AUDIENCE,
            certs_url=IAP_CERTS_URL,
        )
    # google-auth delegates JWK-set verification to PyJWT and lets its
    # exceptions (malformed token, bad signature, audience mismatch,
    # expiry) propagate alongside its own ValueError.
    except (ValueError, PyJWTError):
        raise HTTPException(status_code=401, detail="Unauthorized. Invalid IAP assertion.")

    if claims.get("iss") != IAP_ISSUER:
        raise HTTPException(status_code=401, detail="Unauthorized. Invalid issuer.")

    return dict(claims)


def _validate_user_info(user_info: dict[str, Any]) -> None:
    """Validates that a user is allowed to access the server.

    Args:
        user_info (dict): The verified claims from the IAP assertion.

    Raises:
        HTTPException: If the user is not allowed to access the server.
    """
    if IAP_PUBLIC_ACCESS:
        return  # Authorization is delegated to the proxy.

    if user_info.get("email", "") not in IAP_ALLOW_LIST:
        raise HTTPException(status_code=401, detail="Unauthorized. Not in allowlist.")


@router.get("/login/iap")
async def login(
    x_goog_iap_jwt_assertion: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db_connection),
) -> RedirectResponse:
    """Authenticates a user with a Google Cloud IAP signed-header assertion.

    IAP adds a signed assertion header to every request it proxies, so there
    is no redirect dance: validating the header is the whole login flow.

    Args:
        x_goog_iap_jwt_assertion (str | None): The IAP assertion header.
        db (Session): The database session object.

    Returns:
        RedirectResponse: A redirect response to the UI server with JWT tokens
        set as cookies.

    Raises:
        HTTPException: If the assertion is missing or invalid, or the user is
        not authorized.
    """
    if not x_goog_iap_jwt_assertion:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized. Missing X-Goog-IAP-JWT-Assertion header.",
        )

    user_info = _validate_iap_assertion(x_goog_iap_jwt_assertion)

    user_email = user_info.get("email", "")
    if not user_email:
        raise HTTPException(
            status_code=401, detail="Unauthorized. Assertion has no email claim."
        )

    _validate_user_info(user_info)

    db_user = get_user_by_email_from_db(db, email=user_email)
    if not db_user:
        # IAP assertions don't carry profile claims (name, picture), so the
        # email address doubles as the display name.
        new_user = schemas.UserCreate(
            display_name=user_email,
            username=user_email,
            email=user_email,
            auth_method="iap",
            profile_picture_url="",
            uuid=uuid.uuid4(),
        )
        db_user = create_user_in_db(db, new_user)

    refresh_token = create_jwt_token(
        audience="browser-client",
        expire_minutes=REFRESH_TOKEN_EXPIRE_MINUTES,
        subject=db_user.uuid.hex,
        token_type="refresh",
    )

    access_token = create_jwt_token(
        audience="browser-client",
        expire_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        subject=db_user.uuid.hex,
        token_type="access",
    )

    response = RedirectResponse(url=UI_SERVER_URL)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    response.set_cookie(key="csrf_token", value=generate_csrf_token(), httponly=True)

    return response
