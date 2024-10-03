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

from uuid import UUID

from pydantic import BaseModel

from datetime import datetime
from typing import Optional, List


def custom_uuid_encoder(uuid_object):
    """Return the HEX string representation of the UUID field."""
    if isinstance(uuid_object, UUID):
        return uuid_object.hex


class BaseSchema(BaseModel):
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    is_deleted: Optional[bool] = False

    class Config:
        json_encoders = {UUID: custom_uuid_encoder}


class BaseSchemaCompact(BaseModel):
    id: Optional[int] = None

    class Config:
        json_encoders = {UUID: custom_uuid_encoder}


# User schemas
class User(BaseSchema):
    display_name: str
    username: str
    email: str
    profile_picture_url: str
    uuid: UUID
    is_active: bool


class UserCreate(BaseModel):
    display_name: str
    username: str
    password_hash: Optional[str] = None
    password_hash_algorithm: Optional[str] = None
    auth_method: str
    email: Optional[str] = None
    profile_picture_url: Optional[str] = None
    uuid: UUID
    is_admin: Optional[bool] = False
    is_active: Optional[bool] = True
    is_robot: Optional[bool] = False


class UserResponse(BaseSchema):
    display_name: str
    username: str
    email: Optional[str]
    auth_method: str
    profile_picture_url: Optional[str]
    uuid: UUID


class UserResponseCompact(BaseSchemaCompact):
    display_name: str
    username: str
    email: Optional[str]
    auth_method: str
    profile_picture_url: Optional[str]
    uuid: UUID


class UserApiKeyRequest(BaseModel):
    display_name: str
    description: Optional[str] = ""


class UserApiKeyCreate(BaseSchema):
    display_name: str
    description: str
    token_jti: str
    token_exp: datetime
    user_id: int


class UserApiKeyResponse(BaseSchema):
    display_name: str
    description: str
    token_exp: datetime


# Folder schemas
class FolderCreateRequest(BaseModel):
    display_name: str
    parent_id: Optional[int] = None


class FolderUpdateRequest(BaseModel):
    display_name: str


class FolderCreate(BaseSchema):
    display_name: str
    parent_id: Optional[int] = None


class FolderResponse(BaseSchema):
    display_name: str
    description: Optional[str]
    uuid: UUID
    user: UserResponseCompact
    parent: Optional["FolderResponse"] = None
    selectable: Optional[bool] = False
    workflows: Optional[List["WorkflowResponse"]]


# File schemas
class FileCreate(BaseModel):
    display_name: str
    description: Optional[str] = None
    uuid: UUID
    filename: str
    filesize: Optional[int] = None
    extension: Optional[str] = None
    magic_text: Optional[str] = None
    magic_mime: Optional[str] = None
    data_type: Optional[str] = None
    hash_md5: Optional[str] = None
    hash_sha1: Optional[str] = None
    hash_sha256: Optional[str] = None
    hash_ssdeep: Optional[str] = None
    user_id: Optional[int] = None
    folder_id: Optional[int] = None
    task_output_id: Optional[int] = None


class FileResponse(BaseSchema):
    display_name: str
    description: Optional[str]
    uuid: UUID
    filename: str
    filesize: int
    extension: Optional[str] = None
    magic_text: Optional[str] = None
    magic_mime: Optional[str] = None
    data_type: str
    hash_md5: Optional[str] = None
    hash_sha1: Optional[str] = None
    hash_sha256: Optional[str] = None
    hash_ssdeep: Optional[str] = None
    user_id: int
    user: UserResponseCompact
    folder: Optional[FolderResponse]
    workflows: List["WorkflowResponse"]
    summaries: List["FileSummaryResponse"]


class FileResponseCompact(BaseSchemaCompact):
    uuid: UUID
    is_deleted: Optional[bool] = False
    display_name: str
    filesize: int


class FileSummaryCreate(BaseModel):
    summary: str = ""
    llm_model_prompt: str = ""
    status_short: str = ""
    runtime: float = 0.0
    file_id: int


class FileSummaryResponse(BaseSchemaCompact):
    summary: Optional[str] = ""
    status_short: Optional[str] = None
    status_detail: Optional[str] = None
    status_progress: Optional[str] = None
    runtime: Optional[float] = 0.0
    llm_model_prompt: Optional[str] = None
    llm_model_provider: Optional[str] = None
    llm_model_name: Optional[str] = None
    llm_model_config: Optional[str] = None
    file_id: Optional[int] = None


class CloudDiskCreateRequest(BaseModel):
    folder_id: int
    disk_name: str


# Workflow schemas
class Workflow(BaseSchema):
    display_name: str | None = None
    description: Optional[str] = None
    spec_json: Optional[str] = None
    uuid: Optional[UUID] = None
    user_id: int | None = None
    file_ids: List[int] = []
    folder_id: Optional[int] = None


class WorkflowInputFile(BaseSchemaCompact):
    display_name: str
    data_type: str


class WorkflowFolder(BaseSchemaCompact):
    pass


class WorkflowResponse(BaseSchema):
    display_name: str
    description: Optional[str] = None
    spec_json: Optional[str] = None
    uuid: Optional[UUID] = None
    user: UserResponseCompact
    files: Optional[List["WorkflowInputFile"]]
    tasks: Optional[List["TaskResponse"]]
    folder: Optional["WorkflowFolder"]


class WorkflowStatusResponse(BaseSchema):
    tasks: Optional[List["TaskResponse"]]


class WorkflowCreateRequest(BaseModel):
    folder_id: int
    file_ids: List[int]
    template_id: Optional[int] = None


class WorkflowTemplateCreateRequest(BaseModel):
    display_name: str
    description: Optional[str] = ""
    workflow_id: int


class WorkflowTemplateCreate(BaseModel):
    display_name: str
    description: Optional[str] = None
    spec_json: str
    user_id: int


class WorkflowTemplateResponse(BaseSchema):
    display_name: str
    description: Optional[str] = None
    spec_json: str
    user_id: int


class Task(BaseSchema):
    display_name: str
    description: Optional[str]
    uuid: Optional[UUID] = None
    config: Optional[str]
    status_short: Optional[str]
    status_detail: Optional[str]
    status_progress: Optional[str]
    result: Optional[str]
    runtime: Optional[float]
    error_exception: Optional[str]
    error_traceback: Optional[str]
    user: User
    workflow: Workflow

    class Config:
        from_attributes = True


class TaskResponse(BaseSchema):
    display_name: Optional[str]
    description: Optional[str]
    uuid: Optional[UUID] = None
    status_short: Optional[str]
    status_detail: Optional[str]
    status_progress: Optional[str]
    result: Optional[str]
    runtime: Optional[float]
    error_exception: Optional[str]
    error_traceback: Optional[str]
    user: UserResponseCompact
    output_files: Optional[List[FileResponseCompact]]
