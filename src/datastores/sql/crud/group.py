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

from typing import List

from sqlalchemy.orm import Session

from api.v1 import schemas
from datastores.sql.models.group import Group, GroupRole
from datastores.sql.models.user import User


def get_groups_from_db(db: Session):
    """Get all groups.

    Args:
        db (Session): database session

    Returns:
        list: list of groups
    """
    return db.query(Group).all()


def get_group_from_db(db: Session, group_id: int):
    """Represent a group in the database.

    Args:
        db: SQLAlchemy session
        group_id: Group id

    Returns:
        Group object
    """
    return db.query(Group).filter(Group.id == group_id).first()


def get_group_by_name_from_db(db: Session, name: str):
    """Get a group by name.

    Args:
        db: SQLAlchemy session
        name: Group name

    Returns:
        Group object
    """
    return db.query(Group).filter(Group.name == name).first()


def create_group_in_db(db: Session, new_group: schemas.GroupCreate):
    """Create a group in the database.
    
    Pre-condition: The group name must be unique.
    Post-condition: The group is created in the database.

    Args:
        db: SQLAlchemy session
        new_group: Group object

    Returns:
        Group object
    """
    new_db_group = Group(
        name=new_group.name,
        description=new_group.description,
        uuid=uuid.uuid4().hex,
    )
    db.add(new_db_group)
    db.commit()
    db.refresh(new_db_group)
    return new_db_group


def add_user_to_group(db: Session, group: Group, user: User):
    """Add a user to a group.

    Args:
        db: SQLAlchemy session
        group_id: Group id
        user_id: User id
    """
    group.users.append(user)
    db.commit()
    db.refresh(group)

def add_users_to_group(db: Session, group: Group, users: List[str]):
    """Adds users to a group.

    Args:
        db: SQLAlchemy session
        group_id: Group id
        user_ids: User id
    """
    for username in users:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            continue
        if user in group.users:
            continue
        group.users.append(user)
    db.commit()
    db.refresh(group)

def remove_user_from_group(db: Session, group: Group, user: User):
    """Remove a user from a group.

    Args:
        db: SQLAlchemy session
        group_id: Group id
        user_id: User id
    """
    group.users.remove(user)
    db.commit()
    db.refresh(group)

def remove_users_from_group(db: Session, group: Group, users: List[str]):
    """Remove users from a group.

    Args:
        db: SQLAlchemy session
        group_id: Group id
        user_ids: User id
    """
    for username in users:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            continue
        if user not in group.users:
            continue
        group.users.remove(user)
    db.commit()
    db.refresh(group)

def search_groups(db: Session, search_string: str):
    """
    Search for groups based on a search string.

    Args:
        db (Session): database session
        search_string (str): the string to search for

    Returns:
        list: list of groups
    """
    groups = (
        db.query(Group)
        .filter(
            (Group.name.ilike(f"%{search_string}%"))
            | (Group.username.ilike(f"%{search_string}%"))
            | (Group.email.ilike(f"%{search_string}%"))
        )
        .all()
    )
    return groups


def create_group_role_in_db(
    db: Session, role: str, group_id: int, folder_id: int = None, file_id: int = None
):
    group_role = GroupRole(
        role=role, group_id=group_id, folder_id=folder_id, file_id=file_id
    )
    db.add(group_role)
    db.commit()
    return group_role


def delete_group_role_from_db(db: Session, group_role_id: int) -> None:
    group_role = db.query(GroupRole).filter(GroupRole.id == group_role_id).first()
    db.delete(group_role)
    db.commit()
