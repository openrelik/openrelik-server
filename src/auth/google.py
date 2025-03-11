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
from typing import List, Any, Annotated
import uuid

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import RedirectResponse
from google.auth.transport import requests
from google.oauth2 import id_token
from google.auth import exceptions as google_exceptions

from api.v1 import schemas
from config import config
from datastores.sql.crud.user import create_user_in_db, get_user_by_email_from_db
from datastores.sql.database import get_db_connection

from .common import UI_SERVER_URL, create_jwt_token, generate_csrf_token

router = APIRouter()
oauth = OAuth()

GOOGLE_CLIENT_ID = config["auth"]["google"]["client_id"]
GOOGLE_CLIENT_SECRET = config["auth"]["google"]["client_secret"]
GOOGLE_ALLOW_LIST = config["auth"]["google"]["allowlist"]
GOOGLE_PUBLIC_ACCESS = config["auth"]["google"].get("public_access", False)
GOOGLE_WORKSPACE_DOMAIN = config["auth"]["google"].get("workspace_domain", False)
GOOGLE_EXTRA_AUDIENCES = config["auth"]["google"].get("extra_audiences", [])
REFRESH_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_cookie_refresh_expire_minutes"]
ACCESS_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_cookie_access_expire_minutes"]

oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    client_kwargs={"scope": "openid email profile"},
)


def _validate_google_token(token: str, expected_audiences: List[str]) -> dict[str, Any]:
    """Validates a Google ID token.

    Args:
        token (str): The ID token to validate.
        expected_audience (str): The expected audience for the token.

    Raises:
        HTTPException: If the token is invalid or the audience is not expected.
    """
    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request())
        if idinfo["aud"] not in expected_audiences:
            raise HTTPException(
                status_code=401, detail="Unauthorized. Could not verify audience."
            )
        return idinfo
    except ValueError as e:
        raise HTTPException(status_code=401, detail="Unauthorized. Invalid token.")
    except google_exceptions.GoogleAuthError as e:
        raise HTTPException(
            status_code=401, detail="Unauthorized. Could not verify token."
        )


def _validate_user_info(user_info: dict[str, Any]) -> None:
    # Restrict logins to Google Workspace Domain if configured.
    if GOOGLE_WORKSPACE_DOMAIN and user_info.get("hd") != GOOGLE_WORKSPACE_DOMAIN:
        raise HTTPException(
            status_code=401, detail="Unauthorized. Invalid workspace domain."
        )

    # Check if the user is allowed to login.
    if GOOGLE_PUBLIC_ACCESS:
        pass  # Let everyone in.
    elif not user_info.get("email", "") in GOOGLE_ALLOW_LIST:
        raise HTTPException(status_code=401, detail="Unauthorized. Not in allowlist.")


@router.get("/auth/google/token")
async def auth_header_token(
    x_goog_id_token: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db_connection),
):
    """Handles OpenRelik token generation for a user that provides a valid Google
        authentication token. Used by API clients.

    Args:
        x_goog_id_token (str | None): The Google ID token in the header.
        db (Session): The database session object.

    Returns:
        dict: OpenRelik refresh and access tokens.
    """
    if not x_goog_id_token:
        raise HTTPException(
            status_code=401, detail="Unauthorized, missing x-google-id-token header."
        )

    # Validate the JWT token's aud, exp and signature.
    expected_audiences = [*GOOGLE_EXTRA_AUDIENCES, GOOGLE_CLIENT_ID]
    user_info = _validate_google_token(x_goog_id_token, expected_audiences)

    # Validate the user is actually allowed based on OpenRelik config.
    _validate_user_info(user_info)

    user_email = user_info.get("email", "")
    db_user = get_user_by_email_from_db(db, email=user_email)
    if not db_user:
        new_user = schemas.UserCreate(
            display_name=user_info.get("name", ""),
            username=user_email,
            email=user_email,
            auth_method="google",
            profile_picture_url=user_info.get("picture", ""),
            uuid=uuid.uuid4(),
        )
        db_user = create_user_in_db(db, new_user)

    # Create JWT access token with default expiry time.
    refresh_token = create_jwt_token(
        audience="api-client",
        expire_minutes=REFRESH_TOKEN_EXPIRE_MINUTES,
        subject=db_user.uuid.hex,
        token_type="refresh",
    )

    # Create JWT access token with default expiry time.
    access_token = create_jwt_token(
        audience="api-client",
        expire_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        subject=db_user.uuid.hex,
        token_type="access",
    )

    return {
        "x-openrelik-refresh-token": refresh_token,
        "x-openrelik-access-token": access_token,
    }


@router.get("/login/google")
async def login(request: Request):
    """Redirects the user to the Google authentication endpoint.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        Response: The FastAPI response object.
    """
    redirect_uri = str(request.url_for("auth"))

    workspace_domain = None
    if GOOGLE_WORKSPACE_DOMAIN:
        workspace_domain = GOOGLE_WORKSPACE_DOMAIN

    return await oauth.google.authorize_redirect(
        request, redirect_uri, hd=workspace_domain
    )


@router.get("/auth/google")
async def auth(request: Request, db: Session = Depends(get_db_connection)):
    """Handles the Google authentication callback and issues a JWT access token to the
        authorized user.

    Args:
        request (Request): The FastAPI request object.
        db (Session): The database session object.

    Returns:
        RedirectResponse: A redirect response to the UI server with the JWT access token
        set as a cookie.

    Raises:
        HTTPException: If the user is not authorized or an error occurs during
        authentication.
    """
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as error:
        return {"OAuth error": error.error}

    user_info = token.get("userinfo")
    user_email = user_info.get("email", "")

    _validate_user_info(user_info)

    db_user = get_user_by_email_from_db(db, email=user_email)
    if not db_user:
        new_user = schemas.UserCreate(
            display_name=user_info.get("name", ""),
            username=user_email,
            email=user_email,
            auth_method="google",
            profile_picture_url=user_info.get("picture", ""),
            uuid=uuid.uuid4(),
        )
        db_user = create_user_in_db(db, new_user)

    # Create JWT access token with default expiry time.
    refresh_token = create_jwt_token(
        audience="browser-client",
        expire_minutes=REFRESH_TOKEN_EXPIRE_MINUTES,
        subject=db_user.uuid.hex,
        token_type="refresh",
    )

    # Create JWT access token with default expiry time.
    access_token = create_jwt_token(
        audience="browser-client",
        expire_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        subject=db_user.uuid.hex,
        token_type="access",
    )

    # Create response redirect
    response = RedirectResponse(url=UI_SERVER_URL)
    # Set the JWT cookie in the response
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    response.set_cookie(key="csrf_token", value=generate_csrf_token(), httponly=True)

    return response
