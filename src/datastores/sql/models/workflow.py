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

from sqlalchemy import ForeignKey, UnicodeText, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import BaseModel
from .file import file_workflow_association_table, file_task_input_association_table

if TYPE_CHECKING:
    from .file import File
    from .folder import Folder
    from .user import User


class Workflow(BaseModel):
    display_name: Mapped[str] = mapped_column(UnicodeText, index=True)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True))
    spec_json: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    # Relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="workflows")
    folder_id: Mapped[Optional[int]] = mapped_column(ForeignKey("folder.id"))
    folder: Mapped[Optional["Folder"]] = relationship(back_populates="workflows")
    files: Mapped[List["File"]] = relationship(
        secondary=file_workflow_association_table, back_populates="workflows"
    )
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="Task.id.asc()",
    )


class WorkflowTemplate(BaseModel):
    display_name: Mapped[str] = mapped_column(UnicodeText, index=True)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    spec_json: Mapped[str] = mapped_column(UnicodeText, index=False)
    # Relationships
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id"))
    user: Mapped[Optional["User"]] = relationship(back_populates="workflow_templates")


class Task(BaseModel):
    display_name: Mapped[str] = mapped_column(UnicodeText, index=True)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True))
    config: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    status_short: Mapped[Optional[str]] = mapped_column(UnicodeText, index=True)
    status_detail: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    status_progress: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    result: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    runtime: Mapped[Optional[float]] = mapped_column(index=False)
    error_exception: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    error_traceback: Mapped[Optional[str]] = mapped_column(UnicodeText, index=False)
    # Relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="tasks")
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflow.id"))
    workflow: Mapped["Workflow"] = relationship(back_populates="tasks")

    # Many-to-Many Relationship with File (only for input)
    # A task can have many input files, and a File can be input to many tasks.
    input_files: Mapped[List["File"]] = relationship(
        secondary=file_task_input_association_table,
        back_populates="tasks_input",
    )

    # Output Files Relationship (One-to-Many)
    output_files: Mapped[List["File"]] = relationship(
        back_populates="task_output", foreign_keys="[File.task_output_id]"
    )
