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
import enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import BaseModel
from .group import Group

if TYPE_CHECKING:
    from .file import File
    from .folder import Folder
    from .group import Group
    from .user import User


class Role(enum.Enum):
    """Represents a role in the database."""

    OWNER = "Owner"
    EDITOR = "Editor"
    VIEWER = "Viewer"
    NO_ACCESS = "No Access"


class UserRole(BaseModel):
    """Represents a user role in the database."""

    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship("User", back_populates="user_roles")
    folder_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("folder.id"), nullable=True
    )
    folder: Mapped[Optional["Folder"]] = relationship(
        "Folder", back_populates="user_roles"
    )
    file_id: Mapped[Optional[int]] = mapped_column(ForeignKey("file.id"), nullable=True)
    file: Mapped[Optional["File"]] = relationship("File", back_populates="user_roles")


class GroupRole(BaseModel):
    """Represents a group role in the database."""

    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"))
    group: Mapped["Group"] = relationship("Group", back_populates="group_roles")
    folder_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("folder.id"), nullable=True
    )
    folder: Mapped[Optional["Folder"]] = relationship(
        "Folder", back_populates="group_roles"
    )
    file_id: Mapped[Optional[int]] = mapped_column(ForeignKey("file.id"), nullable=True)
    file: Mapped[Optional["File"]] = relationship("File", back_populates="group_roles")
