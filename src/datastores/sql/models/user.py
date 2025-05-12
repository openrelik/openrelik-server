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
import uuid as uuid_module
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import UUID, Boolean, DateTime, Enum, ForeignKey, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import BaseModel
from .group import group_user_association_table
from .role import Role

if TYPE_CHECKING:
    from .file import File, FileChat
    from .folder import Folder
    from .group import Group
    from .workflow import Task, Workflow, WorkflowTemplate


DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 10080


class User(BaseModel):
    """Represents a user in the database.

    Attributes:
        display_name (str): The display name of the user.
        username (str): The username of the user.
        password_hash (str): The hashed password of the user.
        password_hash_algorithm (str): The algorithm used to hash the user's password.
        auth_method (str): The authentication method of the user.
        email (str): The email of the user.
        profile_picture_url (Optional[str]): The URL of the user's profile picture.
        preferences (Optional[str]): The user's preferences.
        uuid (uuid_module.UUID): The UUID of the user.
        is_active (bool): Whether the user is active.
        is_admin (bool): Whether the user is an admin.
        is_robot (bool): Whether the user is a robot account.
    """

    display_name: Mapped[str] = mapped_column(UnicodeText, unique=False, index=True)
    username: Mapped[str] = mapped_column(UnicodeText, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(UnicodeText, unique=True, index=False, nullable=True)
    password_hash_algorithm: Mapped[str] = mapped_column(Unicode(255), index=True, nullable=True)
    auth_method: Mapped[str] = mapped_column(Unicode(255), index=True)
    email: Mapped[str] = mapped_column(UnicodeText, unique=False, index=True, nullable=True)
    profile_picture_url: Mapped[Optional[str]] = mapped_column(
        UnicodeText, unique=False, index=False, nullable=True
    )
    preferences: Mapped[Optional[str]] = mapped_column(
        UnicodeText, unique=False, index=False, nullable=True
    )
    uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_robot: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Relationships
    folders: Mapped[List["Folder"]] = relationship(back_populates="user")
    files: Mapped[List["File"]] = relationship(back_populates="user")
    file_chats: Mapped[List["FileChat"]] = relationship(back_populates="user")
    workflows: Mapped[List["Workflow"]] = relationship(back_populates="user")
    workflow_templates: Mapped[List["WorkflowTemplate"]] = relationship(back_populates="user")
    tasks: Mapped[List["Task"]] = relationship(back_populates="user")
    api_keys: Mapped[List["UserApiKey"]] = relationship(back_populates="user")
    user_roles: Mapped[List["UserRole"]] = relationship(back_populates="user")
    groups: Mapped[List["Group"]] = relationship(
        secondary=group_user_association_table, back_populates="users"
    )


class UserRole(BaseModel):
    """Represents a user role in the database.

    Attributes:
        role (Role): The role of the user.
    """

    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False)

    # Relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="user_roles")
    folder_id: Mapped[Optional[int]] = mapped_column(ForeignKey("folder.id"), nullable=True)
    folder: Mapped[Optional["Folder"]] = relationship(back_populates="user_roles")
    file_id: Mapped[Optional[int]] = mapped_column(ForeignKey("file.id"), nullable=True)
    file: Mapped[Optional["File"]] = relationship(back_populates="user_roles")


class UserApiKey(BaseModel):
    """Represents an API key associated with a user.

    Attributes:
        display_name (str): The display name of the API key.
        description (Optional[str]): The description of the API key.
        token_jti (str): Unique identifier for the JWT refresh token.
        token_exp (DateTime): Expiration date and time of the JWT refresh token.
        user_id (int): The ID of the user associated with the API key.
    """

    display_name: Mapped[str] = mapped_column(UnicodeText, index=True)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    token_jti: Mapped[str] = mapped_column(UnicodeText, index=True, unique=True)
    token_exp: Mapped[DateTime] = mapped_column(DateTime, index=False)
    # Relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="api_keys")
