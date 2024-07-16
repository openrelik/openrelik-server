import os
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, Unicode, UnicodeText
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import config

from ..database import BaseModel
from datastores.sql.models.workflow import Workflow

if TYPE_CHECKING:
    from datastores.sql.models.file import File
    from datastores.sql.models.user import User


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
    uuid: Mapped[str] = mapped_column(Unicode(45), index=True)
    # Relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="folders")
    files: Mapped[List["File"]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )
    workflows: Mapped[List["Workflow"]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )
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
        base_storage_path = config.get("server").get("storage_path")
        return os.path.join(base_storage_path, self.uuid)
