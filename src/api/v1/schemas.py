# Copyright 2024-2026 Google LLC
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

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


def custom_uuid_encoder(uuid_object):
    """Return the HEX string representation of the UUID field."""
    if isinstance(uuid_object, UUID):
        return uuid_object.hex


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    is_deleted: Optional[bool] = False

    @field_serializer("uuid", check_fields=False)
    def serialize_uuid(self, uuid: UUID):
        return custom_uuid_encoder(uuid)


class BaseSchemaCompact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None

    @field_serializer("uuid", check_fields=False)
    def serialize_uuid(self, uuid: UUID):
        return custom_uuid_encoder(uuid)


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
    is_admin: Optional[bool] = False


class UserResponseCompact(BaseSchemaCompact):
    display_name: str
    username: str
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


class UserSearchRequest(BaseModel):
    search_string: str


class UserSearchResponse(BaseSchema):
    display_name: str
    username: str
    profile_picture_url: Optional[str]


class GroupCreate(BaseSchema):
    name: str
    description: Optional[str] = None
    users: Optional[List[str]] = None


class GroupResponse(BaseSchema):
    name: str
    description: Optional[str] = None


# Folder schemas
class FolderCreateRequest(BaseModel):
    display_name: str
    parent_id: Optional[int] = None
    storage_provider: Optional[str] = None


class FolderUpdateRequest(BaseModel):
    display_name: str


class FolderShareRequest(BaseModel):
    user_ids: Optional[List[int]] = None
    user_names: Optional[List[str]] = None
    group_ids: Optional[List[int]] = None
    group_names: Optional[List[str]] = None
    user_role: Optional[str] = None
    group_role: Optional[str] = None


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
    user_roles: Optional[List["UserRoleResponse"]]
    group_roles: Optional[List["GroupRoleResponse"]]
    storage_provider: Optional[str] = None


class FolderResponseCompact(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    display_name: str
    user: UserResponseCompact
    workflows: Optional[List["WorkflowResponseCompact"]]
    selectable: Optional[bool] = False


class FolderListPaginatedResponse(BaseModel):
    folders: List[FolderResponseCompact]
    page: int
    page_size: int
    total_count: int


class UserRoleResponse(BaseSchema):
    user: UserResponseCompact
    role: str


class GroupRoleResponse(BaseSchema):
    group: GroupResponse
    role: str


# File schemas
class FileCreate(BaseModel):
    display_name: str
    description: Optional[str] = None
    uuid: UUID
    filename: str
    filesize: Optional[int] = None
    extension: Optional[str] = None
    original_path: Optional[str] = None
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
    source_file_id: Optional[int] = None


class FileResponseCompact(BaseSchemaCompact):
    display_name: str
    filesize: int
    uuid: UUID
    folder_id: int
    is_deleted: Optional[bool] = False


class FileResponse(BaseSchema):
    display_name: str
    description: Optional[str]
    uuid: UUID
    filename: str
    filesize: int
    extension: Optional[str] = None
    original_path: Optional[str] = None
    magic_text: Optional[str] = None
    magic_mime: Optional[str] = None
    data_type: str
    hash_md5: Optional[str] = None
    hash_sha1: Optional[str] = None
    hash_sha256: Optional[str] = None
    hash_ssdeep: Optional[str] = None
    storage_provider: Optional[str] = None
    storage_key: Optional[str] = None
    user_id: int
    user: UserResponseCompact
    folder: Optional[FolderResponse] = None
    source_file: Optional[FileResponseCompact]
    summaries: List["FileSummaryResponse"]
    reports: List["FileReportResponse"]


# This is used for the folder list
class FileResponseCompactList(BaseModel):
    id: Optional[int] = None
    display_name: str
    filesize: int
    data_type: str
    magic_mime: Optional[str] = None
    user: UserResponseCompact
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: Optional[bool] = False


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


class FileReportCreate(BaseModel):
    summary: str = ""
    priority: int = 100
    input_file_uuid: str = None
    content_file_uuid: str = None


class FileReportResponse(BaseModel):
    summary: str = ""
    priority: int = 100
    markdown: str = ""
    task: "TaskResponseCompact" = None


class FileReportResponseCompact(BaseModel):
    summary: str = ""
    priority: int = 100
    markdown: str = ""
    file: "FileResponseCompact" = None


# Cloud disk schemas
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
    template_id: Optional[int] = None


class WorkflowStatus(BaseModel):
    status: str
    tasks: Optional[List["TaskResponseCompact"]] = []


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
    template: Optional["WorkflowTemplateResponseCompact"]


class WorkflowResponseCompact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str


class WorkflowStatusResponse(BaseSchema):
    tasks: Optional[List["TaskResponse"]]


class WorkflowCreateRequest(BaseModel):
    folder_id: int
    file_ids: List[int]
    template_id: Optional[int] = None
    template_params: Optional[dict] = None


class WorkflowRunRequest(BaseModel):
    workflow_spec: dict


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


class WorkflowTemplateResponseCompact(BaseModel):
    id: int
    display_name: str


class WorkflowGeneratedNameResponse(BaseModel):
    generated_name: str


class WorkflowReportResponse(BaseModel):
    workflow: WorkflowResponseCompact
    markdown: str


class Task(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

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


class TaskReportCreate(BaseModel):
    summary: str = ""
    priority: int = 100
    markdown: str = None


class TaskReportResponseCompact(BaseModel):
    summary: str = ""
    priority: int = 100
    markdown: str = ""


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
    file_reports: Optional[List[FileReportResponseCompact]]
    task_report: Optional[TaskReportResponseCompact]


class TaskResponseCompact(BaseSchema):
    display_name: Optional[str]
    description: Optional[str]
    uuid: Optional[UUID] = None
    status_short: Optional[str]
    user: UserResponseCompact


class MetricsRequest(BaseModel):
    metric_name: str
    range: int
    step: int
    resolution: str
    aggregate: bool


class FileChatRequest(BaseModel):
    prompt: str


class FileChatCreate(BaseModel):
    system_instructions: str
    user_id: int
    file_id: int


class FileChatResponse(BaseSchema):
    title: Optional[str] = None
    history: Optional[list] = None


class FileChatMessageCreate(BaseModel):
    file_chat_id: int
    request_prompt: str
    response_text: str
    runtime: float


class AgentRequest(BaseModel):
    session_id: str
    agent_name: str
    user_message: Optional[str] = None
    function_name: Optional[str] = None
    long_running_tool_id: Optional[str] = None
    invocation_id: Optional[str] = None


class AgentSessionRequest(BaseModel):
    context: str


class AgentSessionResponse(BaseModel):
    session_id: str


class InvestigativeQuestionsRequest(BaseModel):
    goal: str
    context: str


class SQLQueryRequest(BaseModel):
    query: str


class SQLQueryResponse(BaseModel):
    query: str
    result: List[dict]


class SQLGenerateQueryRequest(BaseModel):
    user_request: str


class SQLGenerateQueryResponse(BaseModel):
    user_request: str
    generated_query: str


class SQLSchemasResponse(BaseModel):
    schemas: dict
