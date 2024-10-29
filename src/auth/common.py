import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.security import APIKeyCookie, APIKeyHeader
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from api.v1 import schemas
from config import config
from datastores.sql.crud.user import get_user_by_uuid_from_db
from datastores.sql.models.user import UserApiKey
from datastores.sql.database import get_db_connection

router = APIRouter()

refresh_token_cookie = APIKeyCookie(name="refresh_token", auto_error=False)
refresh_token_header = APIKeyHeader(name="x-openrelik-refresh-token", auto_error=False)

access_token_cookie = APIKeyCookie(name="access_token", auto_error=False)
access_token_header = APIKeyHeader(name="x-openrelik-access-token", auto_error=False)

csrf_token_cookie = APIKeyCookie(name="csrf_token", auto_error=False)


# JWT settings
JWT_SECRET_KEY = config["auth"]["secret_jwt_key"]
JWT_ALGORITHM = config["auth"]["jwt_algorithm"]

# Server settings
API_SERVER_URL = config["server"].get("api_server_url")
UI_SERVER_URL = config["server"].get("ui_server_url")


def generate_csrf_token():
    """Generates a CSRF token."""
    return secrets.token_urlsafe(32)


def raise_credentials_exception(detail: str = "Could not validate credentials"):
    """Raises an HTTPException with a custom or default detail message.

    Args:
        detail (str, optional): The detail message to include in the exception.
    """
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_jwt_token(
    audience: str,
    expire_minutes: int,
    subject: str,
    token_type: str,
    extra_data: dict = {},
):
    """Creates a JWT access token with the given data and expiration time.

    Args:
        audience (str): The audience of the token (browser-client or api-client)
        expires_delta (int): The expiration time in minutes of the token.
        subject (str): The subject of the token (user UUID).
        token_type (str): The type of token to be created, 'access' or 'refresh'.
        extra_data (dict, optional): Additional data to be encoded in the token.

    Returns:
        str: The encoded JWT token.
    """
    jwt_data = extra_data.copy()
    issued_at = datetime.now(timezone.utc)
    not_before = issued_at  # Option to change this later if suport for future valid tokens is needed.
    expire_at = issued_at + timedelta(minutes=expire_minutes)
    issued_by = API_SERVER_URL if API_SERVER_URL else UI_SERVER_URL
    jwt_data.update({"sub": subject})
    jwt_data.update({"iat": issued_at})
    jwt_data.update({"nbf": not_before})
    jwt_data.update({"exp": expire_at})
    jwt_data.update({"iss": issued_by})
    jwt_data.update({"aud": audience})
    jwt_data.update({"jti": uuid.uuid4().hex})
    jwt_data.update({"token_type": token_type})
    encoded_jwt = jwt.encode(jwt_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def validate_jwt_token(
    token: str,
    expected_token_type: str,
    expected_audience: str,
    check_denylist: bool = False,
    db: Session = Depends(get_db_connection),
):
    """Validates a JWT token.

    Args:

    Returns:
        dict: The decoded JWT payload.

    Raises:
        HTTPException: If the token is invalid for any reason.
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            audience=expected_audience,
            issuer=API_SERVER_URL,
            # Options: https://github.com/mpdavis/python-jose/blob/master/jose/jwt.py
            options={
                "verify_signature": True,
                "verify_aud": True,
                "verify_iat": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iss": True,
                "verify_sub": True,
                "verify_jti": True,
                "require_aud": True,
                "require_iat": True,
                "require_exp": True,
                "require_nbf": True,
                "require_iss": True,
                "require_sub": True,
                "require_jti": True,
                "leeway": 0,
            },
        )
    except JWTError as e:
        raise_credentials_exception(detail=f"JWT decode error: {e}")

    # Only allow the expected token type. This prevents a client to use a refresh token as the
    # access token and vice versa.
    if payload["token_type"] != expected_token_type:
        raise_credentials_exception(
            detail=f"Wrong token type: Expected {expected_token_type} but got {payload['token_type']}"
        )

    # Check if the API key has been revoked, i.e it has been deleted by the user.
    # Note: This only check api-client API keys and not Browser tokens.
    # TODO: Consider supporting revoking Browser based tokens as well.
    if check_denylist and expected_audience == "api-client":
        api_key_db = (
            db.query(UserApiKey).filter(UserApiKey.token_jti == payload["jti"]).first()
        )
        if not api_key_db:
            raise_credentials_exception(detail="Invalid API key")

    return payload


async def verify_csrf(
    request: Request,
    access_token_from_cookie: str | None = Depends(access_token_cookie),
    access_token_from_header: str | None = Depends(access_token_header),
    x_csrf_token: str = Header(None),
    csrf_token: str = Cookie(None),
    db: Session = Depends(get_db_connection),
):
    """
    Dependency to verify CSRF token only for non-GET requests.

    Args:
        request (Request): The FastAPI request object.
        access_token_from_cookie (str, optional): The access token from the cookie.
        access_token_from_header (str, optional): The access token from the header.
        x_csrf_token (str, optional): The CSRF token from the X-CSRF-Token header.
        csrf_token (str, optional): The CSRF token from the cookie.

    Yields:
        None: Yields nothing (importand for FastAPI dependency injection).

    Raises:
        HTTPException: If the CSRF token is invalid.
    """
    access_token = access_token_from_cookie or access_token_from_header

    # Determine the expected audience based on the token source.
    expected_audience = "browser-client" if access_token_from_cookie else "api-client"

    validated_token = validate_jwt_token(
        token=access_token,
        expected_token_type="access",
        expected_audience=expected_audience,
        db=db,
    )
    audience = validated_token.get("aud")

    # Check CSRF for Browser clients only, and for state changing set of methods.
    if audience == "browser-client" and request.method not in (
        "GET",
        "HEAD",
        "OPTIONS",
        "TRACE",
    ):
        if not csrf_token or x_csrf_token != csrf_token:
            raise HTTPException(status_code=400, detail="X-CSRF-Token is invalid")
    else:
        pass

    yield


async def get_current_user(
    access_token_from_cookie: str | None = Depends(access_token_cookie),
    access_token_from_header: str | None = Depends(access_token_header),
    db: Session = Depends(get_db_connection),
):
    """Retrieves the currently logged-in user from the request.

    Args:
        access_token_from_cookie (str, optional): Access token from the cookie (browser clients).
        access_token_from_header (str, optional): Access token from the header (api clients).
        db (Session, optional): The database session object.

    Returns:
        User: The currently logged-in user.

    Raises:
        HTTPException: If the user is not authorized or the token is invalid.
    """
    # First check that there is a token in the request at all.
    if not access_token_from_cookie and not access_token_from_header:
        raise_credentials_exception(detail="Token is missing from request")

    # Only allow tokens from cookie or header, not both. This prevents clients to disable
    # CSRF checks by setting both cookies and headers.
    if access_token_from_cookie and access_token_from_header:
        raise_credentials_exception(detail="Only one authentication method allowed")

    access_token = access_token_from_cookie or access_token_from_header

    # Determine the expected audience based on the token source. This prevents a token
    # to be used outside the original requested source. E.g. if an access token is leaked
    # from a browser it cannot be reused for making API calls using a CLI tool.
    expected_audience = "browser-client" if access_token_from_cookie else "api-client"

    payload = validate_jwt_token(
        token=access_token,
        expected_token_type="access",
        expected_audience=expected_audience,
        db=db,
    )
    user_uuid: str = payload.get("sub")
    user = get_user_by_uuid_from_db(db, uuid=user_uuid)
    if not user:
        raise_credentials_exception(detail="No such user")

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


@router.get("/auth/refresh")
async def refresh(
    refresh_token_from_cookie: str | None = Depends(refresh_token_cookie),
    refresh_token_from_header: str | None = Depends(refresh_token_header),
    db: Session = Depends(get_db_connection),
):
    """
    Refresh access token using a refresh token.

    Args:
        refresh_token_from_cookie (str, optional): Refresh token from the cookie (browser clients).
        refresh_token_from_header (str, optional): Refresh token from the header (api clients).

    Returns:
        Response: The FastAPI response object.

    Raises:
        HTTPException: If the user is not authorized or the token is invalid.
    """
    if not refresh_token_from_cookie and not refresh_token_from_header:
        raise_credentials_exception(detail="Token is missing from request")

    refresh_token = refresh_token_from_cookie or refresh_token_from_header

    # Determine the expected audience based on the token source
    expected_audience = "browser-client" if refresh_token_from_cookie else "api-client"

    payload = validate_jwt_token(
        token=refresh_token,
        expected_token_type="refresh",
        expected_audience=expected_audience,
        check_denylist=True,
        db=db,
    )

    if refresh_token_from_cookie:
        expires_in = config["auth"]["jwt_cookie_access_expire_minutes"]
    else:
        expires_in = config["auth"]["jwt_header_default_access_expire_minutes"]

    # Create new access token based on the old token.
    new_access_token = create_jwt_token(
        audience=payload["aud"],
        subject=payload["sub"],
        expire_minutes=expires_in,
        token_type="access",
    )

    # Create a new CSRF token
    new_csrf_token = generate_csrf_token()
    data = jsonable_encoder(
        {"new_access_token": new_access_token, "new_csrf_token": new_csrf_token}
    )

    response = Response(content=json.dumps(data), media_type="application/json")
    # If the client (e.g API client) sends the tokens in the header instead, skip
    # setting cookies.
    if not refresh_token_from_header:
        response.set_cookie(key="access_token", value=new_access_token, httponly=True)
        response.set_cookie(key="csrf_token", value=new_csrf_token, httponly=True)

    return response


@router.get("/auth/csrf")
async def csrf(
    csrf_token_from_cookie: str | None = Depends(csrf_token_cookie),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """
    Returns the CSRF token from the users cookie.

    Args:
        csrf_token_from_cookie (str, optional): CSRF token from the cookie.
        current_user (User): The currently logged-in user.

    Returns:
        str: The CSRF token.
    """
    return csrf_token_from_cookie


@router.post("/auth/logout")
async def logout(response: Response):
    """Logs out the currently logged-in user by deleting the access token cookie.

    Args:
        response (Response): The FastAPI response object.

    Returns:
        dict: A dictionary containing a message indicating the success of the operation.
    """
    response.delete_cookie(key="refresh_token")
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="csrf_token")

    return {"message": "Logged out"}
