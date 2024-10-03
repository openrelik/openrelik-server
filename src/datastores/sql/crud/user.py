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

from sqlalchemy.orm import Session

from api.v1 import schemas
from datastores.sql.models.user import User, UserApiKey


def get_users_from_db(db: Session):
    """Get all users.

    Args:
        db (Session): database session

    Returns:
        list: list of users
    """
    return db.query(User).all()


def get_user_from_db(db: Session, user_id: int):
    """Represent a user in the database.

    Args:
        db: SQLAlchemy session
        user_id: User id

    Returns:
        User object
    """
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email_from_db(db: Session, email: str):
    """Get a user by email.

    Args:
        db: SQLAlchemy session
        email: User email

    Returns:
        User object
    """
    return db.query(User).filter(User.email == email).first()


def get_user_by_uuid_from_db(db: Session, uuid: str):
    """Get a user by UUID.

    Args:
        db: SQLAlchemy session
        uuid: User UUID

    Returns:
        User object
    """
    return db.query(User).filter(User.uuid == uuid).first()


def get_user_by_username_from_db(db: Session, username: str):
    """Get a user by username.

    Args:
        db: SQLAlchemy session
        username: User username

    Returns:
        User object
    """
    return db.query(User).filter(User.username == username).first()


def create_user_in_db(db: Session, new_user: schemas.UserCreate):
    """Create a user in the database.

    Args:
        db: SQLAlchemy session
        user: User object

    Returns:
        User object
    """
    new_db_user = User(
        display_name=new_user.display_name,
        username=new_user.username,
        password_hash=new_user.password_hash,
        password_hash_algorithm=new_user.password_hash_algorithm,
        auth_method=new_user.auth_method,
        email=new_user.email,
        profile_picture_url=new_user.profile_picture_url,
        uuid=new_user.uuid,
        is_admin=new_user.is_admin,
        is_active=new_user.is_active,
        is_robot=new_user.is_robot,
    )
    db.add(new_db_user)
    db.commit()
    db.refresh(new_db_user)
    return new_db_user


def get_user_api_keys_from_db(db: Session, current_user: User):
    """Get a list of user api keys.

    Args:
        db: SQLAlchemy session
        current_user: User object

    Returns:
        List of UserApiKey objects
    """
    return db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).all()


def create_user_api_key_in_db(db: Session, apikey: schemas.UserApiKeyCreate):
    """Create a user api key in the database.

    Args:
        db: SQLAlchemy session
        apikey: UserApiKey object

    Returns:
        UserApiKey object
    """
    new_apikey = UserApiKey(
        display_name=apikey.display_name,
        description=apikey.description,
        token_jti=apikey.token_jti,
        token_exp=apikey.token_exp,
        user_id=apikey.user_id,
    )
    db.add(new_apikey)
    db.commit()
    db.refresh(new_apikey)
    return new_apikey


def delete_user_api_key_from_db(db: Session, apikey_id: int, current_user: User):
    """Delete a user api key from the database.

    Args:
        db: SQLAlchemy session
        apikey_id: UserApiKey ID
        current_user: User object
    """
    api_key = (
        db.query(UserApiKey)
        .filter(UserApiKey.id == apikey_id, UserApiKey.user_id == current_user.id)
        .first()
    )
    if api_key:
        db.delete(api_key)
        db.commit()
