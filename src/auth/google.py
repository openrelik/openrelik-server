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
import uuid

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import RedirectResponse

from api.v1 import schemas
from config import config
from datastores.sql.crud.user import create_user_in_db, get_user_by_email_from_db
from datastores.sql.database import get_db_connection

from .common import UI_SERVER_URL, create_jwt_token

router = APIRouter()
oauth = OAuth()

GOOGLE_CLIENT_ID = config["auth"]["google"]["client_id"]
GOOGLE_CLIENT_SECRET = config["auth"]["google"]["client_secret"]
GOOGLE_ALLOW_LIST = config["auth"]["google"]["allowlist"]

REFRESH_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_cookie_refresh_expire_minutes"]
ACCESS_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_cookie_access_expire_minutes"]

oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/login/google")
async def login(request: Request):
    """Redirects the user to the Google authentication endpoint.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        Response: The FastAPI response object.
    """
    redirect_uri = str(request.url_for("auth"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


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

    # Return early if the user is not allowed on the server.
    if not user_email in GOOGLE_ALLOW_LIST:
        raise HTTPException(status_code=401, detail="Unauthorized")

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

    return response
