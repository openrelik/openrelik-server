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

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from datastores.sql.models.user import User, UserApiKey

from api.v1 import schemas


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


def create_user_in_db(db: Session, user: schemas.User):
    """Create a user in the database.

    Args:
        db: SQLAlchemy session
        user: User object

    Returns:
        User object
    """
    new_user = User(name=user.name, email=user.email, picture=user.picture)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


def get_user_api_keys_from_db(db: Session, current_user: User):
    """Get a list of user api keys.

    Args:
        db: SQLAlchemy session
        current_user: User object

    Returns:
        List of UserApiKey objects
    """
    return db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).all()


def get_user_access_token_from_db(db: Session, api_key: str):
    """Get a user access token from an api key.

    Args:
        db: SQLAlchemy session
        api_key: API key

    Returns:
        UserApiKey object
    """
    return db.query(UserApiKey).filter(UserApiKey.api_key == api_key).first()


def create_user_api_key_in_db(db: Session, apikey: schemas.UserApiKey):
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
        api_key=apikey.api_key,
        access_token=apikey.access_token,
        user_id=apikey.user_id,
    )
    new_apikey.expires_at = datetime.now() + timedelta(minutes=apikey.expire_minutes)
    db.add(new_apikey)
    db.commit()
    db.refresh(new_apikey)
    return new_apikey
