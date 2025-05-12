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
    Column,
    ForeignKey,
    Integer,
    Table,
    Unicode,
    UnicodeText,
    event,
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
    from .group import GroupRole
    from .user import User, UserRole
    from .workflow import Task, Workflow


file_workflow_association_table = Table(
    "file_workflow_association_table",
    BaseModel.metadata,
    Column("file_id", ForeignKey("file.id"), primary_key=True),
    Column("workflow_id", ForeignKey("workflow.id"), primary_key=True),
)

# Many to many relationship for File and Task, where a File can be an input to many
# Tasks and a Task can have many input Files.
file_task_input_association_table = Table(
    "file_task_input_association",
    BaseModel.metadata,
    Column("task_id", ForeignKey("task.id"), primary_key=True),
    Column("file_id", ForeignKey("file.id"), primary_key=True),
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

    # Many-to-Many Relationship with Task (only for input files)
    tasks_input: Mapped[List["Task"]] = relationship(
        secondary=file_task_input_association_table,
        back_populates="input_files",
        order_by="Task.id.desc()",
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

    chats: Mapped[List["FileChat"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )

    reports: Mapped[List["FileReport"]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
        foreign_keys="FileReport.file_id",
    )

    # One-to-one relationship for report content
    report_content: Mapped["FileReport"] = relationship(
        back_populates="content_file",
        cascade="all, delete-orphan",
        foreign_keys="FileReport.content_file_id",
        uselist=False,
    )

    # Optional relationship to represent files extracted from a source file
    # (e.g., from a disk image). This is a self reference, i.e. pointing to
    # another File object.
    source_file_id: Mapped[Optional[int]] = mapped_column(ForeignKey("file.id"))
    source_file: Mapped[Optional["File"]] = relationship(
        "File", remote_side="File.id", backref="extracted_files"
    )

    # Roles, used by the permission system.
    user_roles: Mapped[List["UserRole"]] = relationship(back_populates="file")
    group_roles: Mapped[List["GroupRole"]] = relationship(back_populates="file")

    @hybrid_property
    def path(self):
        """Returns the full path of the file."""
        filename = self.uuid.hex
        if self.extension:
            filename = f"{filename}.{self.extension}"
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


class FileReport(BaseModel):
    """Represents a report on a file.

    Attributes:
        summary (str): The summary of the report.
        priority (int): The priority of the report.
        markdown (str): The markdown content of the report.
    """

    summary: Mapped[str] = mapped_column(UnicodeText, index=False)
    priority: Mapped[int] = mapped_column(Integer, index=True)
    markdown: Mapped[str] = mapped_column(UnicodeText, index=False)

    # The file that this report is about.
    file_id: Mapped[int] = mapped_column(ForeignKey("file.id"))
    file: Mapped["File"] = relationship(back_populates="reports", foreign_keys=[file_id])

    # The task that created this report.
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task.id"))
    task: Mapped[Optional["Task"]] = relationship(
        back_populates="file_reports", foreign_keys=[task_id]
    )

    # The file containing the report content. One-to-one relationship.
    content_file_id: Mapped[int] = mapped_column(ForeignKey("file.id"))
    content_file: Mapped["File"] = relationship(
        back_populates="report_content",
        foreign_keys=[content_file_id],
        uselist=False,
    )


class FileChat(BaseModel):
    """Represents a chat for a file in the database.

    Attributes:
        title (Optional[str]): The title of the chat.
        system_instructions (str): The system instructions for the chat.
        uuid (uuid_module.UUID): The UUID of the chat.
        incognito (bool): Indicates whether the chat is in incognito mode (no history saved).
        user_id (int): The ID of the user who created the chat.
        file_id (int): The ID of the file associated with the chat.
        messages (List[FileChatMessage]): The messages in the chat.
    """

    title: Mapped[Optional[str]] = mapped_column(UnicodeText, index=True)
    system_instructions: Mapped[str] = mapped_column(UnicodeText, index=False)
    uuid: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, default=uuid_module.uuid4()
    )
    incognito: Mapped[bool] = mapped_column(index=True, default=False)

    # Relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="file_chats")

    file_id: Mapped[int] = mapped_column(ForeignKey("file.id"))
    file: Mapped["File"] = relationship(back_populates="chats")

    summaries: Mapped[List["FileChatSummary"]] = relationship(
        back_populates="file_chat", cascade="all, delete-orphan"
    )

    messages: Mapped[List["FileChatMessage"]] = relationship(
        back_populates="file_chat", cascade="all, delete-orphan"
    )

    def get_chat_history(self):
        """Returns the messages in the chat in a format for the LLM."""
        history = []
        for message in self.messages:
            history.extend(
                [
                    {
                        "role": "user",
                        "content": message.request_prompt,
                    },
                    {
                        "role": "assistant",
                        "content": message.response_text,
                    },
                ]
            )
        return history


class FileChatSummary(BaseModel):
    """Represents a summary of a file chat.

    Attributes:
        summary (str): The summary of the chat.
        uuid (uuid_module.UUID): The UUID of the chat summary.
        is_shared (bool): Visible to everyone that has access to the File.
        runtime (float): The runtime of the chat.
        status_short (str): The short status of the chat.
        status_detail (str): The detail status of the chat.
        status_progress (str): The progress status of the chat.
        model_prompt (str): The prompt used to generate the summary.
        model_provider (str): The provider of the model used to generate the summary.
        model_name (str): The name of the model used to generate the summary.
        model_config (str): The configuration of the model used to generate the summary.
        file_chat_id (int): The ID of the file chat being summarized.
        file_chat (FileChat): The file chat being summarized.
    """

    summary: Mapped[str] = mapped_column(UnicodeText, index=False)
    uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    is_shared: Mapped[bool] = mapped_column(index=True, default=False)
    runtime: Mapped[Optional[float]] = mapped_column(index=True)

    # Status of processing the summary
    status_short: Mapped[Optional[str]] = mapped_column(UnicodeText, index=True)
    status_detail: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    status_progress: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)

    # LLM model details
    llm_model_prompt: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    llm_model_provider: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    llm_model_name: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    llm_model_config: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)

    # Relationships
    file_chat_id: Mapped[int] = mapped_column(ForeignKey("filechat.id"))
    file_chat: Mapped["FileChat"] = relationship(back_populates="summaries")


class FileChatMessage(BaseModel):
    """Represents a message in a file chat.

    Attributes:
        request_prompt (str): The prompt sent to the LLM.
        response_text (str): The response from the LLM.
        uuid (uuid_module.UUID): The UUID of the message.
        runtime (Optional[float]): The runtime of the message.
        llm_model_provider (Optional[str]): The provider of the LLM model.
        llm_model_name (Optional[str]): The name of the LLM model.
        llm_model_config (Optional[str]): The configuration of the LLM model.
        file_chat_id (int): The ID of the file chat this message belongs to.
        file_chat (FileChat): The file chat this message belongs to.
        user_id (int): The ID of the user who created the message.
        user (User): The user who created the message.
        feedbacks (List[FileChatMessageFeedback]): The feedbacks on the message.
    """

    request_prompt: Mapped[str] = mapped_column(UnicodeText, index=False)
    response_text: Mapped[str] = mapped_column(UnicodeText, index=False)
    uuid: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, default=uuid_module.uuid4()
    )
    runtime: Mapped[Optional[float]] = mapped_column(index=True)

    # LLM model details
    llm_model_provider: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    llm_model_name: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    llm_model_config: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)

    # Relationships
    file_chat_id: Mapped[int] = mapped_column(ForeignKey("filechat.id"))
    file_chat: Mapped["FileChat"] = relationship(back_populates="messages")

    feedbacks: Mapped[List["FileChatMessageFeedback"]] = relationship(
        back_populates="file_chat_message", cascade="all, delete-orphan"
    )


class FileChatMessageFeedback(BaseModel, FeedbackMixin):
    """Represents feedback on a FileChatMessage.

    This class get base attributes from FeedbackMixin and adds a relationship to the
    FileChatMessage model.

    Attributes from FeedbackMixin:
        upvote (bool): Indicates whether the user upvoted the message.
        downvote (bool): Indicates whether the user downvoted the message.
        feedback_text (str): Optional text feedback from the user.
        user_id (int): The ID of the user who created the feedback
        user (User): The user who created the feedback

    Attributes:
        file_chat_message_id (int): The ID of the FileChatMessage being given feedback on.
        file_chat_message (FileChatMessage): The FileChatMessage being given feedback on.
    """

    # Relationships
    file_chat_message_id: Mapped[int] = mapped_column(ForeignKey("filechatmessage.id"))
    file_chat_message: Mapped["FileChatMessage"] = relationship(back_populates="feedbacks")


# Delete file from the filesystem when the database row is deleted.
@event.listens_for(File, "after_delete")
def delete_file_after_row_delete(mapper, connection, file_to_delete):
    if os.path.exists(file_to_delete.path):
        os.remove(file_to_delete.path)
