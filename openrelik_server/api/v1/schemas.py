from pydantic import BaseModel

from datetime import datetime
from typing import Optional, List


class BaseSchema(BaseModel):
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# User schemas
class User(BaseSchema):
    name: str
    email: str
    picture: str
    is_active: Optional[bool] = True

    class Config:
        from_attributes = True


class UserResponseCompact(BaseModel):
    id: int
    name: str
    email: str
    picture: str


class UserApiKey(BaseSchema):
    display_name: Optional[str] = None
    description: Optional[str] = None
    api_key: Optional[str] = None
    access_token: Optional[str] = None
    expire_minutes: Optional[int] = None
    user_id: Optional[int] = None

    class Config:
        from_attributes = True


class UserApiKeyResponse(BaseSchema):
    display_name: Optional[str] = None
    description: Optional[str] = None
    api_key: Optional[str] = None
    expires_at: Optional[datetime] = None


# class Folder(BaseSchema):
#    display_name: str
#    description: Optional[str] = None
#    user: Optional[User] = None


# Folder schemas
class FolderCreateRequest(BaseSchema):
    display_name: str
    parent_id: Optional[int] = None


class FolderResponse(BaseSchema):
    display_name: str
    description: Optional[str]
    uuid: str
    user: UserResponseCompact
    parent: Optional["FolderResponse"] = None
    selectable: Optional[bool] = False
    workflows: Optional[List["WorkflowResponse"]]


class FolderResponseCompact(BaseSchema):
    id: int


# File schemas
class NewFileRequest(BaseModel):
    display_name: str
    description: Optional[str] = None
    uuid: str
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

    class Config:
        from_attributes = True


class FileResponse(BaseModel):
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    display_name: str
    description: Optional[str]
    uuid: str
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


class FileResponseCompact(BaseModel):
    id: int
    display_name: str


class FileSummary(BaseModel):
    summary: str = ""
    llm_model_prompt: str = ""
    status_short: str = ""
    runtime: float = 0.0
    file_id: int

    class Config:
        from_attributes = True


class FileSummaryResponse(BaseModel):
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
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


# Workflow schemas
class Workflow(BaseSchema):
    display_name: str | None = None
    description: Optional[str] = None
    spec_json: Optional[str] = None
    uuid: Optional[str] = None
    user_id: int | None = None
    file_ids: List[int] = []
    folder_id: Optional[int] = None

    class Config:
        from_attributes = True


class WorkflowFile(BaseSchema):
    id: int
    display_name: str


class WorkflowFolder(BaseSchema):
    id: int


class WorkflowResponse(BaseSchema):
    display_name: str
    description: Optional[str] = None
    spec_json: Optional[str] = None
    uuid: Optional[str] = None
    user: UserResponseCompact
    files: Optional[List["WorkflowFile"]]
    tasks: Optional[List["TaskResponse"]]
    folder: Optional["WorkflowFolder"]


class WorkflowStatusResponse(BaseSchema):
    tasks: Optional[List["TaskResponse"]]


class WorkflowCreateRequest(BaseSchema):
    folder_id: int
    file_ids: List[int]
    template_id: Optional[int] = None


class WorkflowTemplate(BaseSchema):
    display_name: str
    description: Optional[str] = None
    spec_json: str
    user_id: int

    class Config:
        from_attributes = True


class WorkflowTemplateRequest(BaseSchema):
    display_name: Optional[str] = None
    description: Optional[str] = None
    workflow: WorkflowResponse


class Task(BaseSchema):
    display_name: str
    description: Optional[str]
    uuid: Optional[str]
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
    uuid: Optional[str]
    status_short: Optional[str]
    status_detail: Optional[str]
    status_progress: Optional[str]
    result: Optional[str]
    runtime: Optional[float]
    error_exception: Optional[str]
    error_traceback: Optional[str]
    user: UserResponseCompact
    output_files: Optional[List[FileResponseCompact]]
