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

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth.common import (
    create_jwt_token,
    validate_jwt_token,
    get_current_active_user,
    get_db_connection,
)

from datastores.sql.crud.user import (
    get_user_api_keys_from_db,
    create_user_api_key_in_db,
    delete_user_api_key_from_db,
)

from api.v1 import schemas
from config import config

router = APIRouter()


@router.get("/me/")
def get_current_user(
    user: schemas.User = Depends(get_current_active_user),
) -> schemas.UserResponse:
    """
    Get the current user.

    Args:
        user (schemas.User): The current user.

    Returns:
        schemas.User: The current user.
    """
    return user


@router.get("/me/apikeys/")
async def get_api_key_for_current_user(
    current_user: schemas.User = Depends(get_current_active_user),
    db: Session = Depends(get_db_connection),
) -> list[schemas.UserApiKeyResponse]:
    """
    Get the API keys for the current user.

    Args:
        current_user (schemas.User): The current user.
        db (Session): The database session.

    Returns:
        list[schemas.UserApiKeyResponse]: The API keys for the current user.
    """
    return get_user_api_keys_from_db(db, current_user=current_user)


@router.post("/me/apikeys/")
async def create_api_key_for_current_user(
    request: schemas.UserApiKeyRequest,
    current_user: schemas.User = Depends(get_current_active_user),
    db: Session = Depends(get_db_connection),
):
    """Create an API key for the current user.

    Args:
        user_api_key (schemas.UserApiKey): The API key to create.
        current_user (schemas.User): The current user.
        db (Session): The database session.

    Returns:
        schemas.UserApiKeyResponse: The created API key.
    """
    TOKEN_EXPIRE_MINUTES = config["auth"]["jwt_header_default_refresh_expire_minutes"]
    refresh_token = create_jwt_token(
        audience="api-client",
        expire_minutes=TOKEN_EXPIRE_MINUTES,
        subject=current_user.uuid.hex,
        token_type="refresh",
    )
    payload = validate_jwt_token(
        refresh_token,
        expected_token_type="refresh",
        expected_audience="api-client",
    )
    new_api_key = schemas.UserApiKeyCreate(
        display_name=request.display_name,
        description=request.description,
        token_jti=payload["jti"],
        token_exp=payload["exp"],
        user_id=current_user.id,
    )
    create_user_api_key_in_db(db, new_api_key)
    return {"token": refresh_token, "display_name": request.display_name}


@router.delete("/me/apikeys/{apikey_id}")
async def delete_api_key(
    apikey_id: int,
    current_user: schemas.User = Depends(get_current_active_user),
    db: Session = Depends(get_db_connection),
):
    """Delete an API key for the current user.

    Args:
        apikey_id (int): The ID of the API key to delete.
        current_user (schemas.User): The current user.
        db (Session): The database session.
    """
    delete_user_api_key_from_db(db, apikey_id=apikey_id, current_user=current_user)
