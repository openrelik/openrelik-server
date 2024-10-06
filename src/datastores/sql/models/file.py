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

from sqlalchemy import (
    UUID,
    BigInteger,
    ForeignKey,
    Unicode,
    UnicodeText,
    event,
    Column,
    Table,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import (
    AttributeMixin,
    BaseModel,
    FeedbackMixin,
)

if TYPE_CHECKING:
    from .folder import Folder
    from .user import User
    from .workflow import Task, Workflow

file_workflow_association_table = Table(
    "file_workflow_association_table",
    BaseModel.metadata,
    Column("file_id", ForeignKey("file.id"), primary_key=True),
    Column("workflow_id", ForeignKey("workflow.id"), primary_key=True),
)


class File(BaseModel):
    """Represents a file in the database.

    Attributes:
        display_name (Optional[str]): The display name of the file.
        description (Optional[str]): The description of the file.
        uuid (str): The UUID of the file.
        filename (str): The filename of the file.
        filesize (int): The size of the file.
        extension (str): The file extension of the file.
        original_path (str): The original path of the file.
        magic_text (str): The magic text of the file.
        magic_mime (str): The magic mime of the file.
        data_type (str): The data type of the file.
        hash_md5 (str): The MD5 hash of the file.
        hash_sha1 (str): The SHA1 hash of the file.
        hash_sha256 (str): The SHA256 hash of the file.
        hash_ssdeep (str): The SSDEEP hash of the file.
        user_id (int): The ID of the user who uploaded the file.
        user (User): The user who uploaded the file.
        folder_id (Optional[int]): The ID of the folder containing the file.
        folder (Folder): The folder containing the file.
        workflows (List[Workflow]): The workflows that have been applied to the file.
        summaries (List[FileSummary]): The summaries of the file.
    """

    display_name: Mapped[Optional[str]] = mapped_column(UnicodeText, index=True)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True))
    data_type: Mapped[str] = mapped_column(UnicodeText, index=True)

    # From the original file
    filename: Mapped[str] = mapped_column(UnicodeText, index=True)
    filesize: Mapped[Optional[int]] = mapped_column(BigInteger, index=False)
    extension: Mapped[str] = mapped_column(UnicodeText, index=True)
    original_path: Mapped[Optional[str]] = mapped_column(UnicodeText, index=True)

    # Metadata
    magic_text: Mapped[Optional[str]] = mapped_column(UnicodeText, index=True)
    magic_mime: Mapped[Optional[str]] = mapped_column(UnicodeText, index=True)
    hash_md5: Mapped[Optional[str]] = mapped_column(Unicode(32), index=True)
    hash_sha1: Mapped[Optional[str]] = mapped_column(Unicode(40), index=True)
    hash_sha256: Mapped[Optional[str]] = mapped_column(Unicode(64), index=True)
    hash_ssdeep: Mapped[Optional[str]] = mapped_column(Unicode(255), index=True)

    # Relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="files")
    folder_id: Mapped[Optional[int]] = mapped_column(ForeignKey("folder.id"))
    folder: Mapped[Optional["Folder"]] = relationship(back_populates="files")

    # Relationship to Task (Input File)
    task_input_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task.id"))
    task_input: Mapped[Optional["Task"]] = relationship(
        back_populates="input_files", foreign_keys=[task_input_id]
    )

    # Relationship to Task (Output File)
    task_output_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task.id"))
    task_output: Mapped[Optional["Task"]] = relationship(
        back_populates="output_files", foreign_keys=[task_output_id]
    )

    workflows: Mapped[List["Workflow"]] = relationship(
        secondary=file_workflow_association_table,
        back_populates="files",
        order_by="Workflow.id.desc()",
    )
    attributes: Mapped[List["FileAttribute"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    summaries: Mapped[List["FileSummary"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )

    # Optional relationship to represent files extracted from a source file
    # (e.g., from a disk image). This is a self reference, i.e. pointing to
    # another File object.
    source_file_id: Mapped[Optional[int]] = mapped_column(ForeignKey("file.id"))
    source_file: Mapped[Optional["File"]] = relationship(
        "File", remote_side="File.id", backref="extracted_files"
    )

    @hybrid_property
    def path(self):
        """Returns the full path of the file."""
        filename = f"{self.uuid.hex}"
        return os.path.join(self.folder.path, filename)


class FileAttribute(BaseModel, AttributeMixin):
    """Represents an attribute associated with a file.

    This class get base attributes from AttributeMixin and adds a relationship to the
    File model.

    Attributes from AttributeMixin:
        key (str): The key of the attribute.
        value (str): The value of the attribute.
        ontology (str): The ontology of the attribute.
        description (str): The description of the attribute.
        user_id (int): The ID of the user who created the attribute.
        user (User): The user who created the attribute.

    Attributes:
        file_id (int): The ID of the file the attribute is associated with.
        file (File): The file the attribute is associated with.
    """

    file_id: Mapped[int] = mapped_column(ForeignKey("file.id"))
    file: Mapped["File"] = relationship(back_populates="attributes")


class FileSummary(BaseModel):
    """Represents a summary of a file in the database.

    Attributes:
        summary (str): The summary of the file.
        runtime (float): The runtime of the file.
        status_short (str): The short status of the file.
        status_detail (str): The detail status of the file.
        status_progress (str): The progress status of the file.
        model_prompt (str): The prompt used to generate the file.
        model_provider (str): The provider of the model used to generate the file.
        model_name (str): The name of the model used to generate the file.
        model_config (str): The configuration of the model used to generate the file.
        file_id (int): The ID of the file being summarized.
        file (File): The file being summarized.
        feedbacks (List[FileSummaryFeedback]): The feedbacks on the summary.
    """

    summary: Mapped[str] = mapped_column(UnicodeText, index=False)
    runtime: Mapped[Optional[float]] = mapped_column(index=True)
    status_short: Mapped[Optional[str]] = mapped_column(UnicodeText, index=True)
    status_detail: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    status_progress: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    # LLM model details
    llm_model_prompt: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    llm_model_provider: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    llm_model_name: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    llm_model_config: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    # Relationships
    file_id: Mapped[int] = mapped_column(ForeignKey("file.id"))
    file: Mapped["File"] = relationship(back_populates="summaries")

    feedbacks: Mapped[List["FileSummaryFeedback"]] = relationship(
        back_populates="filesummary", cascade="all, delete-orphan"
    )


class FileSummaryFeedback(BaseModel, FeedbackMixin):
    """Represents feedback on a FileSummary.

    This class get base attributes from FeedbackMixin and adds a relationship to the
    FileSummary model.

    Attributes from FeedbackMixin:
        upvote (bool): Indicates whether the user upvoted the summary.
        downvote (bool): Indicates whether the user downvoted the summary.
        feedback_text (str): Optional text feedback from the user.
        user_id (int): The ID of the user who created the feedback
        user (User): The user who created the feedback

    Attributes:
        filesummary_id (int): The ID of the FileSummary being given feedback on.
        filesummary (FileSummary): The FileSummary being given feedback on.
    """

    # Relationships
    filesummary_id: Mapped[int] = mapped_column(ForeignKey("filesummary.id"))
    filesummary: Mapped["FileSummary"] = relationship(back_populates="feedbacks")


# Delete file from the filesystem when the database row is deleted.
@event.listens_for(File, "after_delete")
def delete_file_after_row_delete(mapper, connection, file_to_delete):
    if os.path.exists(file_to_delete.path):
        os.remove(file_to_delete.path)
