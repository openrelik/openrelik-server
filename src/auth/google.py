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
from datetime import datetime, timedelta, timezone

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import APIKeyCookie, APIKeyHeader
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from config import config
from datastores.sql.crud.user import (
    create_user_in_db,
    get_user_by_email_from_db,
    get_user_access_token_from_db,
)
from datastores.sql.database import get_db_connection
from api.v1 import schemas


router = APIRouter()
oauth = OAuth()

cookie_scheme = APIKeyCookie(name="access_token", auto_error=False)
api_key_header = APIKeyHeader(name="x-openrelik-apikey", auto_error=False)

GOOGLE_CLIENT_ID = config["auth"]["google"]["client_id"]
GOOGLE_CLIENT_SECRET = config["auth"]["google"]["client_secret"]
UI_SERVER_URL = config["server"]["ui_server_url"]
USER_ALLOW_LIST = config["auth"]["allowlist"]

oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    client_kwargs={"scope": "openid email profile"},
)

# JWT settings
SECRET_KEY = config["auth"]["secret_jwt_key"]
ALGORITHM = config["auth"]["jwt_algorithm"]
ACCESS_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_expire_minutes"]


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """Creates a JWT access token with the given data and expiration time.

    Args:
        data (dict): The data to be encoded in the token.
        expires_delta (timedelta | None, optional): The expiration time of the token.
            If None, the token will expire after 10080 minutes (7 days).

    Returns:
        str: The encoded JWT access token.
    """
    to_encode = data.copy()
    access_token_expires = timedelta(expires_delta)
    expire = datetime.now(timezone.utc) + access_token_expires
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    cookie: str | None = Depends(cookie_scheme),
    api_key: str | None = Depends(api_key_header),
    db: Session = Depends(get_db_connection),
):
    """Retrieves the currently logged-in user from the request.

    Args:
        cookie (str | None, optional): The access token cookie.
        api_key (str | None, optional): The API key.
        db (Session, optional): The database session object.

    Returns:
        User: The currently logged-in user.

    Raises:
        HTTPException: If the user is not authorized or the token is invalid.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = None
    if not cookie and not api_key:
        raise credentials_exception

    if api_key:
        access_token = get_user_access_token_from_db(db, api_key)
        # Check if token has expired
        if access_token.expires_at < datetime.now():
            raise credentials_exception
        token = access_token.access_token

    token = token or cookie

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise credentials_exception

    except JWTError:
        raise credentials_exception
    user = get_user_by_email_from_db(db, email=email)
    if not user:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: schemas.User = Depends(get_current_user),
):
    """Retrieves the currently logged-in active user from the request.

    Args:
        current_user (User): The currently logged-in user.

    Returns:
        User: The currently logged-in active user.

    Raises:
        HTTPException: If the user is not active.
    """
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


@router.get("/login")
async def login(request: Request):
    """Redirects the user to the Google authentication endpoint.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        Response: The FastAPI response object.
    """
    redirect_uri = str(request.url_for("auth"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth")
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
        return HTMLResponse(f"<h1>{error.error}</h1>")
    user_info = token.get("userinfo")
    user_email = user_info.get("email", "")

    # Return early if the user is not allowed on the server.
    if not user_email in USER_ALLOW_LIST:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db_user = get_user_by_email_from_db(db, email=user_email)
    if not db_user:
        new_user = schemas.UserCreate(
            name=user_info.get("name", ""),
            email=user_email,
            picture=user_info.get("picture", ""),
            uuid=uuid.uuid4(),
        )
        db_user = create_user_in_db(db, new_user)

    # Create JWT access token
    access_token = create_access_token(
        data={"sub": db_user.email},
        expires_delta=ACCESS_TOKEN_EXPIRE_MINUTES,
    )

    # Create response redirect
    response = RedirectResponse(url=UI_SERVER_URL)
    # Set the JWT cookie in the response
    response.set_cookie(key="access_token", value=access_token, httponly=True)

    return response


@router.delete("/logout")
async def logout(response: Response):
    """Logs out the currently logged-in user by deleting the access token cookie.

    Args:
        response (Response): The FastAPI response object.

    Returns:
        dict: A dictionary containing a message indicating the success of the operation.
    """
    response.delete_cookie(key="access_token")
    return {"message": "Logged out"}
