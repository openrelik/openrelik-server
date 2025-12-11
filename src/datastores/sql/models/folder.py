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
    from datastores.sql.models.group import GroupRole
    from datastores.sql.models.user import User, UserRole


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

    # Root-level folders only: The storage provider name is used to identify where the folder is
    # stored. The name is used to lookup the storage provider configuration, which contains the
    # mount point. Only root-level folders have this set; subfolders inherit the storage provider of
    # their top-level parent folder. This attribute is ignored for subfolders.
    storage_provider: Mapped[str] = mapped_column(UnicodeText, index=True, nullable=True)

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
        """Returns the full path of the folder, accounting for old root-level folders.

        Returns:
            str: The full path of the folder.
        """
        is_root_folder = not self.parent

        def _get_root_base_path(storage_provider: Optional[str] = None) -> str:
            """Helper to get the base storage path for a root folder from the config.

            Args:
                storage_provider: The storage provider name.

            Returns:
                str: The base storage path.
            """
            current_config = get_config()
            storage_provider_configs = (
                current_config.get("server", {}).get("storage", {}).get("providers", {})
            )
            base_path = None

            if storage_provider_configs:
                if storage_provider:
                    provider_config = storage_provider_configs.get(storage_provider)
                    if provider_config:
                        base_path = provider_config.get("path")
                
                # This is a fallback for legacy root folders with no storage provider set.
                # This relies on the server_default provider being set in the config which is part
                # of the migration to the new config format.
                if not base_path:
                    default_provider = storage_provider_configs.get("server_default", {})
                    base_path = default_provider.get("path")

            # Fallback path for old config format. If no storage provider is set in the config, use
            # the storage_path from the old config format.
            if not base_path:
                base_path = current_config.get("server", {}).get("storage_path")

            return base_path

        # If the folder has a storage provider set, use it to determine the base path.
        # This allows any folder (root or subfolder) to be a "mount point" for a storage provider.
        if self.storage_provider:
             base_storage_path = _get_root_base_path(self.storage_provider)
             return os.path.join(base_storage_path, self.uuid.hex)

        # If the folder is a root folder (no parent) and has no storage provider set,
        # use the default base storage path from the config.
        if is_root_folder:
            base_storage_path = _get_root_base_path()
            return os.path.join(base_storage_path, self.uuid.hex)

        parent_path = self.parent.path
        return os.path.join(parent_path, self.uuid.hex)

    def get_effective_storage_provider(self):
        """Returns the effective storage provider for the folder.
        
        This recursively traverses up the folder hierarchy to find the storage provider.
        If no provider is explicitly set on the folder or its ancestors, it returns
        the default provider (None or 'server_default' implicitly).

        Returns:
            str: The effective storage provider name.
        """
        if self.storage_provider:
            return self.storage_provider
        
        if self.parent:
            return self.parent.get_effective_storage_provider()
        
        # If root and no provider, it uses the server default implicitly.
        # We return None to represent "inherited/default" which effectively maps
        # to the server_default in the config logic.
        return None


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
