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
import os
import uuid as uuid_module
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import UUID, BigInteger, ForeignKey, Integer, UnicodeText
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import get_config
from datastores.sql.models.workflow import Workflow

from ..database import AttributeMixin, BaseModel

if TYPE_CHECKING:
    from datastores.sql.models.file import File
    from datastores.sql.models.user import User, UserRole
    from datastores.sql.models.group import GroupRole


class Folder(BaseModel):
    """Represents a folder in the database.

    Attributes:
        display_name: The display name of the folder.
        description: The description of the folder.
        uuid: The UUID of the folder.
        user_id: The ID of the user who owns the folder.
        user: The user who owns the folder.
        files: The files in the folder.
        workflows: The workflows in the folder.
        parent_id: The ID of the parent folder.
        parent: The parent folder.
        children: The children folders.
    """

    display_name: Mapped[str] = mapped_column(UnicodeText, index=True)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True))

    # Relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="folders")
    files: Mapped[List["File"]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )
    workflows: Mapped[List["Workflow"]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )
    attributes: Mapped[List["FolderAttribute"]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )

    # Roles, used by the permission system.
    user_roles: Mapped[List["UserRole"]] = relationship(back_populates="folder")
    group_roles: Mapped[List["GroupRole"]] = relationship(back_populates="folder")

    # Implements an adjacency list relationship to support folders in folders.
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), ForeignKey("folder.id")
    )

    parent: Mapped[Optional["Folder"]] = relationship(
        "Folder", back_populates="children", remote_side="Folder.id"
    )
    children: Mapped[List["Folder"]] = relationship("Folder", back_populates="parent")

    @hybrid_property
    def path(self):
        """Returns the full path of the folder."""
        current_config = get_config()
        base_storage_path = current_config.get("server").get("storage_path")
        return os.path.join(base_storage_path, self.uuid.hex)


class FolderAttribute(BaseModel, AttributeMixin):
    """Represents an attribute associated with a folder.

    This class get base attributes from AttributeMixin and adds a relationship to the
    Folder model.

    Attributes from AttributeMixin:
        key (str): The key of the attribute.
        value (str): The value of the attribute.
        ontology (str): The ontology of the attribute.
        description (str): The description of the attribute.
        user_id (int): The ID of the user who created the attribute.
        user (User): The user who created the attribute.
    """

    folder_id: Mapped[int] = mapped_column(ForeignKey("folder.id"))
    folder: Mapped["Folder"] = relationship(back_populates="attributes")


class FolderSummary(BaseModel):
    """Represents a summary of a folder in the database.

    Attributes:
        summary (str): The summary of the folder.
        runtime (float): The runtime of the folder.
        status_short (str): The short status of the folder.
        status_detail (str): The detail status of the folder.
        status_progress (str): The progress status of the folder.
        model_prompt (str): The prompt used to generate the folder.
        model_provider (str): The provider of the model used to generate the folder.
        model_name (str): The name of the model used to generate the folder.
        model_config (str): The configuration of the model used to generate the folder.
        folder_id (int): The ID of the folder being summarized.
        folder (Folder): The folder being summarized.
    """

    summary: Mapped[str] = mapped_column(UnicodeText, index=False)
    runtime: Mapped[Optional[float]] = mapped_column(index=True)
    status_short: Mapped[Optional[str]] = mapped_column(UnicodeText, index=True)
    status_detail: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    status_progress: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    # LLM model details
    llm_model_prompt: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    llm_model_provider: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
