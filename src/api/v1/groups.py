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

from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from auth.common import get_current_active_user, authenticated_as_admin

from api.v1 import schemas
from datastores.sql.database import get_db_connection
from datastores.sql.models.group import Group
from datastores.sql.models.user import User
from datastores.sql.crud.group import (
    create_group_in_db,
    add_users_to_group,
    remove_users_from_group,
)

router = APIRouter()


@router.get("/")
def get_all_groups(
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.GroupResponse]:
    """
    Get all groups.

    Args:
        db (Session): The database session.

    Returns:
        List of groups.
    """
    return db.query(Group).all()


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_group(
    group_request: schemas.GroupCreate,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(authenticated_as_admin),
) -> schemas.GroupResponse:
    """
    Create a new group, optionally adding users to it.

    Args:
        group_request (schemas.GroupCreate): The request body containing group details.
        db (Session): The database session.
        current_user (schemas.User): The currently authenticated user.

    Returns:
        schemas.GroupResponse: The created group.
    """
    existing_group = db.query(Group).filter(Group.name == group_request.name).first()
    if existing_group and existing_group.name == group_request.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Group with name {group_request.name} already exists.",
        )
    new_group = create_group_in_db(db, group_request)
    if group_request.users:
        add_users_to_group(db, new_group, group_request.users)
    group_response = schemas.GroupResponse.model_validate(
        new_group, from_attributes=True
    )
    return group_response


@router.get("/{group_name}/users")
def get_group_users(
    group_name: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.UserResponse]:
    """
    Get all users in a group.
    Args:
        group_name (str): The name of the group.
        db (Session): The database session.
        current_user (schemas.User): The currently authenticated user.
    Returns:
        List of users in the group.
    """
    group = db.query(Group).filter(Group.name == group_name).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with name {group_name} not found.",
        )
    users = group.users
    return [
        schemas.UserResponse.model_validate(user, from_attributes=True)
        for user in users
    ]


@router.post("/{group_name}/users")
def add_users_to_group_endpoint(
    group_name: str,
    user_requests: List[str],
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(authenticated_as_admin),
) -> List[schemas.UserResponse]:
    """
    Add users to a group.
    Args:
        group_name (str): The name of the group.
        user_requests (List[str]): List of users to add.
        db (Session): The database session.
        current_user (schemas.User): The currently authenticated user.
    Returns:
        List of users added to the group.
    """
    group = db.query(Group).filter(Group.name == group_name).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with name {group_name} not found.",
        )
    users = []
    for user_request in user_requests:
        user = db.query(User).filter(User.username == user_request).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with username {user_request} not found.",
            )
        if user in group.users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with username {user_request} is already in group {group_name}.",
            )
        users.append(user)
    add_users_to_group(db, group, user_requests)
    return [
        schemas.UserResponse.model_validate(user, from_attributes=True)
        for user in users
    ]


@router.delete("/{group_name}/users")
def remove_users_from_group_endpoint(
    group_name: str,
    user_requests: List[str],
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(authenticated_as_admin),
) -> List[schemas.UserResponse]:
    """
    Remove users from a group.
    Args:
        group_name (str): The name of the group.
        user_requests (List[str]): List of users to remove.
        db (Session): The database session.
        current_user (schemas.User): The currently authenticated user.
    Returns:
        List of users removed from the group.
    """
    group = db.query(Group).filter(Group.name == group_name).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with name {group_name} not found.",
        )
    users = []
    for user_request in user_requests:
        user = db.query(User).filter(User.username == user_request).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with username {user_request} not found.",
            )
        if user not in group.users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with username {user_request} is not in group {group_name}.",
            )
        users.append(user)
    remove_users_from_group(db, group, user_requests)
    return [
        schemas.UserResponse.model_validate(user, from_attributes=True)
        for user in users
    ]


@router.delete("/{group_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_name: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(authenticated_as_admin),
) -> JSONResponse:
    """
    Delete a group.
    Args:
        group_name (str): The name of the group to delete.
        db (Session): The database session.
        current_user (schemas.User): The currently authenticated user.
    Returns:
        JSONResponse: A response indicating the result of the deletion.
    """
    group = db.query(Group).filter(Group.name == group_name).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with name {group_name} not found.",
        )
    db.delete(group)
    db.commit()
    return JSONResponse(
        status_code=status.HTTP_204_NO_CONTENT,
        content={"message": "Group deleted successfully."},
    )
