import argon2
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from datastores.sql.crud.user import get_user_by_username_from_db
from datastores.sql.database import get_db_connection

from config import config
from .common import UI_SERVER_URL, create_jwt_token

from starlette.responses import RedirectResponse, Response


router = APIRouter()
password_hasher = argon2.PasswordHasher()

REFRESH_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_cookie_refresh_expire_minutes"]
ACCESS_TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_cookie_access_expire_minutes"]


@router.post("/auth/local")
async def auth_local(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db_connection),
):
    """Authenticates a user with local username and password.

    Args:
        request (Request): The FastAPI request object.
        form_data (OAuth2PasswordRequestForm): Contains the username and password.
        db (Session): The database session object.

    Returns:
        RedirectResponse: A redirect response to the UI server with the JWT access token
        set as a cookie.

    Raises:
        HTTPException: If the username or password is invalid.
    """
    db_user = get_user_by_username_from_db(db, username=form_data.username)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    try:
        password_hasher.verify(db_user.password_hash, form_data.password)
    except argon2.exceptions.VerifyMismatchError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

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

    print(refresh_token)
    print(access_token)

    # Create response redirect
    response = Response()

    print(response, UI_SERVER_URL)

    # Set the JWT cookie in the response
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True)
    response.set_cookie(key="access_token", value=access_token, httponly=True)

    return response
