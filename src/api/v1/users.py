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

import secrets

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth.google import create_access_token, get_current_active_user, get_db_connection

from datastores.sql.crud.user import (
    get_user_api_keys_from_db,
    create_user_api_key_in_db,
)

from api.v1 import schemas


router = APIRouter()


@router.get("/me/", response_model=schemas.User)
def get_current_user(user: schemas.User = Depends(get_current_active_user)):
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
    user_api_key: schemas.UserApiKey,
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
    user_api_key.access_token = create_access_token(
        data={"sub": current_user.email},
        expires_delta=user_api_key.expire_minutes,
    )
    user_api_key.user_id = current_user.id
    user_api_key.api_key = secrets.token_hex(32)
    return create_user_api_key_in_db(db, user_api_key)
