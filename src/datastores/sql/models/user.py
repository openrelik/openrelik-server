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

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import BaseModel

if TYPE_CHECKING:
    from .file import File
    from .folder import Folder
    from .workflow import Workflow, WorkflowTemplate, Task


DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 10080


class User(BaseModel):
    """Represents a user in the database.

    Attributes:
        name (str): The name of the user.
        email (str): The email address of the user.
        picture (str): The URL of the user's profile picture.
        preferences (str): A JSON string containing the user's preferences.
        is_active (bool): Whether the user is active.
        folders (List[Folder]): The folders owned by the user.
        files (List[File]): The files owned by the user.
        workflows (List[Workflow]): The workflows created by the user.
        workflow_templates (List[WorkflowTemplate]): The workflow templates created by the user.
        tasks (List[Task]): The tasks assigned to the user.
        api_keys (List[UserApiKey]): The API keys associated with the user.
    """

    name: Mapped[str] = mapped_column(UnicodeText, unique=False, index=True)
    email: Mapped[str] = mapped_column(UnicodeText, unique=True, index=True)
    picture: Mapped[Optional[str]] = mapped_column(
        UnicodeText, unique=False, index=False
    )
    preferences: Mapped[Optional[str]] = mapped_column(
        UnicodeText, unique=False, index=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Relationships
    folders: Mapped[List["Folder"]] = relationship(back_populates="user")
    files: Mapped[List["File"]] = relationship(back_populates="user")
    workflows: Mapped[List["Workflow"]] = relationship(back_populates="user")
    workflow_templates: Mapped[List["WorkflowTemplate"]] = relationship(
        back_populates="user"
    )
    tasks: Mapped[List["Task"]] = relationship(back_populates="user")
    api_keys: Mapped[List["UserApiKey"]] = relationship(back_populates="user")


class UserApiKey(BaseModel):
    """Represents an API key associated with a user.

    Attributes:
        display_name (Optional[str]): The display name of the API key.
        description (Optional[str]): The description of the API key.
        api_key (Optional[str]): The API key itself.
        access_token (Optional[str]): The access token associated with the API key.
        expires_at (Optional[DateTime]): The expiration time of the access token.
    """

    display_name: Mapped[Optional[str]] = mapped_column(UnicodeText, index=True)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    api_key: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    access_token: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    expires_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, index=False)
    # Relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="api_keys")
