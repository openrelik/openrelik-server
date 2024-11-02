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
from typing import TYPE_CHECKING, List

from sqlalchemy import UUID, Column, ForeignKey, Table, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import BaseModel

if TYPE_CHECKING:
    from .roles import GroupRole
    from .user import User


group_user_association_table = Table(
    "group_user_association_table",
    BaseModel.metadata,
    Column("group_id", ForeignKey("group.id"), primary_key=True),
    Column("user_id", ForeignKey("user.id"), primary_key=True),
)


class Group(BaseModel):
    """Represents a group in the database.

    Attributes:
        display_name (str): The display name of the group.
        description (str): The description of the group.
        uuid (uuid_module.UUID): The UUID of the group.
        users (List[User]): The users in the group.
    """

    display_name: Mapped[str] = mapped_column(UnicodeText, unique=False, index=True)
    description: Mapped[str] = mapped_column(UnicodeText, unique=False, index=False)
    uuid: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, index=True
    )
    users: Mapped[List["User"]] = relationship(
        secondary=group_user_association_table,
        back_populates="groups",
    )
    group_roles: Mapped[List["GroupRole"]] = relationship(back_populates="group")
