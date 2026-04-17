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
from typing import Any

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import RedirectResponse

from api.v1 import schemas
from config import config
from datastores.sql.crud.user import create_user_in_db, get_user_by_email_from_db
from datastores.sql.database import get_db_connection

from .common import UI_SERVER_URL, create_jwt_token, generate_csrf_token

router = APIRouter()
oauth = OAuth()

OIDC_CLIENT_ID = config["auth"]["oidc"]["client_id"]
OIDC_CLIENT_SECRET = config["auth"]["oidc"]["client_secret"]
OIDC_DISCOVERY_URL = config["auth"]["oidc"]["discovery_url"]
OIDC_ALLOW_LIST = config["auth"]["oidc"]["allowlist"]
OIDC_PUBLIC_ACCESS = config["auth"]["oidc"].get("public_access", False)
OIDC_REDIRECT_URI = config["auth"]["oidc"].get("redirect_uri", None)
REFRESH_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_cookie_refresh_expire_minutes"]
ACCESS_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_cookie_access_expire_minutes"]

oauth.register(
    name="oidc",
    server_metadata_url=OIDC_DISCOVERY_URL,
    client_id=OIDC_CLIENT_ID,
    client_secret=OIDC_CLIENT_SECRET,
    client_kwargs={"scope": "openid email profile"},
)


def _validate_user_info(user_info: dict[str, Any]) -> None:
    """Validates that a user is allowed to access the server.

    Args:
        user_info (dict): The user info claims from the OIDC IdP.

    Raises:
        HTTPException: If the user is not allowed to access the server.
    """
    if OIDC_PUBLIC_ACCESS:
        return  # Let everyone in.

    if user_info.get("email", "") not in OIDC_ALLOW_LIST:
        raise HTTPException(status_code=401, detail="Unauthorized. Not in allowlist.")


@router.get("/login/oidc")
async def login(request: Request) -> Any:
    """Redirects the user to the OIDC IdP authentication endpoint.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        Response: The redirect response to the IdP.
    """
    redirect_uri = OIDC_REDIRECT_URI or str(request.url_for("oidc_auth"))
    return await oauth.oidc.authorize_redirect(request, redirect_uri)


@router.get("/auth/oidc")
async def oidc_auth(request: Request, db: Session = Depends(get_db_connection)) -> RedirectResponse:
    """Handles the OIDC authentication callback and issues JWT tokens to the authorized user.

    Args:
        request (Request): The FastAPI request object.
        db (Session): The database session object.

    Returns:
        RedirectResponse: A redirect response to the UI server with JWT tokens set as cookies.

    Raises:
        HTTPException: If the user is not authorized or an error occurs during authentication.
    """
    try:
        token = await oauth.oidc.authorize_access_token(request)
    except OAuthError as error:
        raise HTTPException(status_code=401, detail=f"OAuth error: {error.error}")

    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(status_code=401, detail="Unauthorized. Could not retrieve user info.")

    _validate_user_info(user_info)

    user_email = user_info.get("email", "")
    db_user = get_user_by_email_from_db(db, email=user_email)
    if not db_user:
        new_user = schemas.UserCreate(
            display_name=user_info.get("name", ""),
            username=user_email,
            email=user_email,
            auth_method="oidc",
            profile_picture_url=user_info.get("picture", ""),
            uuid=uuid.uuid4(),
        )
        db_user = create_user_in_db(db, new_user)
    else:
        db_user.display_name = user_info.get("name", db_user.display_name)
        db_user.profile_picture_url = user_info.get("picture", db_user.profile_picture_url)
        db.add(db_user)
        db.commit()

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
