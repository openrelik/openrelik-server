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
import json
import uuid
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from openrelik_ai_common.providers import manager
from sqlalchemy.orm import Session
from sse_starlette import EventSourceResponse

import config
from auth.common import get_current_active_user
from datastores.sql.crud.authz import check_user_access, require_access
from datastores.sql.crud.file import get_files_from_db
from datastores.sql.crud.folder import (
    create_root_folder_in_db,
    create_subfolder_in_db,
    delete_folder_from_db,
    get_all_folders_from_db,
    get_folder_from_db,
    get_root_folders_from_db,
    get_shared_folders_from_db,
    get_subfolders_from_db,
    update_folder_in_db,
)
from datastores.sql.crud.group import (
    create_group_role_in_db,
    delete_group_role_from_db,
    get_group_by_name_from_db,
    get_group_from_db,
    group_role_exists,
)
from datastores.sql.crud.user import (
    create_user_role_in_db,
    delete_user_role_from_db,
    get_user_by_username_from_db,
    get_user_from_db,
    user_role_exists,
)
from datastores.sql.database import get_db_connection
from datastores.sql.models.role import Role

from . import schemas

router = APIRouter()


# Get all root folders for a user
@router.get("/")
def get_root_folders(
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.FolderResponseCompact]:
    """Get all root folders for a user.

    Args:
        db (Session): database session
        current_user (User): current user

    Returns:
        list: list of folders
    """
    return get_root_folders_from_db(db, current_user)


# Get all shared root folders for a user
@router.get("/shared/")
def get_shared_folders(
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.FolderResponseCompact]:
    """Get all shared folders for a user.

    Args:
        db (Session): database session
        current_user (User): current user

    Returns:
        list: list of folders
    """
    return get_shared_folders_from_db(db, current_user)


# Get all shared root folders for a user
@router.get("/all/")
def get_all_folders(
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
    page: int = 1,
    page_size: int = 40,
    q: str | None = None,
) -> schemas.FolderListPaginatedResponse:
    """Get all shared folders for a user.

    Args:
        db (Session): database session
        current_user (User): current user
        q (str | None): search term

    Returns:
        list: list of folders
    """
    result, total_count = get_all_folders_from_db(
        db, current_user, search_term=q, page=page, page_size=page_size
    )
    response = schemas.FolderListPaginatedResponse(
        folders=result,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )
    return response


# Get all sub-folders for a parent folder
@router.get("/{folder_id}/folders/")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_subfolders(
    folder_id: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.FolderResponseCompact]:
    """
    Get all subfolders within a specified folder.

    Args:
        folder_id: The ID of the parent folder.
        db: The database session.
        current_user: The currently authenticated user.

    Returns:
        A list of subfolders within the specified folder.

    Raises:
        HTTPException: If the parent folder does not exist or the user does not have permission to access it.
    """
    return get_subfolders_from_db(db, parent_folder_id=folder_id)


# Get folder
@router.get("/{folder_id}")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_folder(
    folder_id: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.FolderResponse:
    """Get a folder from the database if the user has access.

    Args:
        folder_id: The ID of the folder to retrieve.
        db: The database session.
        current_user: The currently authenticated user.

    Returns:
        The folder object if found and the user has access.

    Raises:
        HTTPException: If the folder does not exist or the user does not have
        permission to access it.
    """
    if not folder_id:
        raise HTTPException(status_code=404, detail="Folder not found.")
    try:
        folder = get_folder_from_db(db, folder_id)
        if folder is None:
            raise HTTPException(status_code=404, detail="Folder not found.")
    except ValueError as exception:
        raise HTTPException(status_code=404, detail=str(exception))
    if folder.is_deleted:
        raise HTTPException(status_code=404, detail="Folder is deleted.")
    return folder


# Create root folder
# No access check is necessary as active users can create their own root folders.
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_root_folder(
    new_folder_request: schemas.FolderCreateRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.FolderResponse:
    """Create a folder.

    Args:
        db (Session): database session
        new_folder_request (dict): dictionary for a folder
        current_user (User): current user

    Returns:
        Folder: folder

    Raises:
        HTTPException: If the user does not have permission to create a folder.
    """
    return create_root_folder_in_db(db, new_folder_request, current_user)


# Create subfolder
@router.post("/{folder_id}/folders/", status_code=status.HTTP_201_CREATED)
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
def create_subfolder(
    new_folder_request: schemas.FolderCreateRequest,
    folder_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.FolderResponse:
    """Create a sub folder.

    Args:
        db (Session): database session
        new_folder_request (dict): dictionary for a folder
        current_user (User): current user

    Returns:
        Folder: folder
    """
    return create_subfolder_in_db(db, folder_id, new_folder_request, current_user)


# Update folder
@router.patch("/{folder_id}")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
async def update_folder(
    folder_id: int,
    folder_from_request: schemas.FolderUpdateRequest,
    current_user: schemas.User = Depends(get_current_active_user),
    db: Session = Depends(get_db_connection),
) -> schemas.FolderResponse:
    """Update a folder in the database.

    Args:
        folder_id (int): The ID of the folder to update.
        folder_from_request (schemas.FolderUpdateRequest): The updated folder data.
        current_user (schemas.User): The currently authenticated user.
        db (Session): The database session.

    Returns:
        schemas.FolderResponse: The updated folder data.

    Raises:
        HTTPException: If the user does not have permission to update it.
    """
    folder_from_db = get_folder_from_db(db, folder_id)
    folder_model = schemas.FolderCreate(**folder_from_db.__dict__)

    # Update folder data with supplied values
    update_data = folder_from_request.model_dump(exclude_unset=True)
    updated_folder_model = folder_model.model_copy(update=update_data)

    return update_folder_in_db(db, updated_folder_model)


# Get files for a folder
@router.get("/{folder_id}/files/")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_folder_files(
    folder_id: str,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[schemas.FileResponseCompactList]:
    return get_files_from_db(db, folder_id)


# Delete folder
@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_access(allowed_roles=[Role.OWNER])
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    delete_folder_from_db(db, folder_id)


# Share folder
@router.post("/{folder_id}/roles")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
def share_folder(
    folder_id: int,
    request: schemas.FolderShareRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.FolderResponse:
    """Share a folder.
    Assigns specified roles to users and groups for the given folder.

    The `@require_access` decorator ensures the current user has EDITOR or OWNER
    permissions on the folder.

    Args:
        folder_id: The ID of the folder to share.
        request: The share request details including users, groups, and roles.
        db: Database session.
        current_user: The currently authenticated user.

    Returns:
        The updated folder information with new roles.

    Raises:
        HTTPException:
            - 400 Bad Request: If an invalid role string is provided.
            - 404 Not Found: If the folder, a user, or a group is not found,
                             or if trying to share a deleted folder.
            - 409 Conflict: If a user or group already has the specified role
                            on the folder.
    """
    folder_to_share = get_folder_from_db(db, folder_id)
    # @require_access handles folder not found, but this is an explicit check.
    if not folder_to_share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found.")
    if folder_to_share.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cannot share a deleted folder.",
        )
    user_permission_role = None
    group_permission_role = None
    try:
        if request.user_ids or request.user_names:
            user_permission_role = Role(request.user_role)
        if request.group_ids or request.group_names:
            group_permission_role = Role(request.group_role)

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role provided. Valid roles are: {[r.value for r in Role]}",
        )

    # Process User IDs
    if request.user_ids:
        for user_id_to_share in request.user_ids:
            user = get_user_from_db(db, user_id_to_share)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with ID {user_id_to_share} not found.",
                )
            # Use enum member's name (e.g., "OWNER") instead of value (e.g., "Owner")
            if user_role_exists(db, user_id_to_share, folder_id, user_permission_role.name):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"User ID {user_id_to_share} already has the role '{user_permission_role.name}' on folder {folder_id}.",
                )
            # Pass enum member's name for creation
            create_user_role_in_db(
                db, user_permission_role.name, user_id_to_share, folder_id=folder_id
            )

    # Process User Names
    if request.user_names:
        for user_name_to_share in request.user_names:
            user = get_user_by_username_from_db(db, user_name_to_share)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with username '{user_name_to_share}' not found.",
                )
            # Use enum member's name (e.g., "OWNER") instead of value (e.g., "Owner")
            if user_role_exists(db, user.id, folder_id, user_permission_role.name):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"User '{user_name_to_share}' (ID: {user.id}) already has the role '{user_permission_role.name}' on folder {folder_id}.",
                )
            # Pass enum member's name for creation
            create_user_role_in_db(db, user_permission_role.name, user.id, folder_id=folder_id)

    # Process Group IDs
    if request.group_ids:
        for group_id_to_share in request.group_ids:
            group = get_group_from_db(db, group_id_to_share)
            if not group:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Group with ID {group_id_to_share} not found.",
                )
            # Use enum member's name (e.g., "OWNER") instead of value (e.g., "Owner")
            if group_role_exists(db, group_id_to_share, folder_id, group_permission_role.name):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Group ID {group_id_to_share} already has the role '{group_permission_role.name}' on folder {folder_id}.",
                )
            # Pass enum member's name for creation
            create_group_role_in_db(
                db, group_permission_role.name, group_id_to_share, folder_id=folder_id
            )

    # Process Group Names
    if request.group_names:
        for group_name_to_share in request.group_names:
            group = get_group_by_name_from_db(db, group_name_to_share)
            if not group:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Group with name '{group_name_to_share}' not found.",
                )
            # Use enum member's name (e.g., "OWNER") instead of value (e.g., "Owner")
            if group_role_exists(db, group.id, folder_id, group_permission_role.name):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Group '{group_name_to_share}' (ID: {group.id}) already has the role '{group_permission_role.name}' on folder {folder_id}.",
                )
            # Pass enum member's name for creation
            create_group_role_in_db(db, group_permission_role.name, group.id, folder_id=folder_id)

    return get_folder_from_db(db, folder_id)


@router.get("/{folder_id}/roles/me")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_my_folder_role(
    folder_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    try:
        folder = get_folder_from_db(db, folder_id)
        return check_user_access(
            db,
            current_user,
            allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER],
            folder=folder,
        )
    except ValueError as exception:
        raise HTTPException(status_code=404, detail=str(exception))


@router.delete("/{folder_id}/roles/groups/{role_id}")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
def delete_group_role(
    folder_id: int,
    role_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    delete_group_role_from_db(db, role_id)


@router.delete("/{folder_id}/roles/users/{role_id}")
@require_access(allowed_roles=[Role.EDITOR, Role.OWNER])
def delete_user_role(
    folder_id: int,
    role_id: int,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    delete_user_role_from_db(db, role_id)


# TODO: Persist questions and answers in the database for later retrieval.Change the route to
# include the question ID in the URL, e.g., /{folder_id}/investigations/questions/{question_id}/run.
@router.post("/{folder_id}/investigations/questions/run")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
async def run_agent(
    folder_id: int,
    request: schemas.AgentRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Run an agent to answer investigative questions.

    This starts a Server-Sent Events (SSE) stream to the Agent Development Kit (ADK) server and
    mediates all ADK events and responses back to the client.

    Args:
        folder_id (int): The ID of the folder to limit file access.
        request (schemas.AgentRequest): The request containing the agent name and question prompt.
        db (Session): The database session.
        current_user (schemas.User): The currently authenticated user.
    """

    ADK_BASE_URL = config.config.get("experiments", {}).get("agents", {}).get("adk_server_url")

    # Ensure the ADK server URL is configured.
    if not ADK_BASE_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADK server URL is not configured.",
        )

    async def _create_adk_session(session_id: str):
        """Creates a new session to ADK for the given app and user.

        Args:
            session_id (str): The unique session ID to create.

        Returns:
            tuple: A tuple containing the response and session ID.
        """
        url = f"{ADK_BASE_URL}/apps/{request.agent_name}/users/{current_user.id}/sessions/{session_id}"
        headers = {"Content-Type": "application/json"}
        payload = {"state": {}}

        try:
            response = httpx.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response, session_id
        except httpx.HTTPStatusError as e:
            print(f"HTTP error creating session: {e.response.status_code} - {e.response.text}")
            return None, session_id
        except httpx.RequestError as e:
            print(f"Request error creating session: {e}")
            return None, session_id

    async def _run_sse_stream():
        """
        Calls the /run_sse endpoint from the ADK server and streams the result back
        using Server-Sent Events (SSE).

        Returns:
            EventSourceResponse: A stream of events from the ADK server.
        """
        url = f"{ADK_BASE_URL}/run_sse"

        session = await _create_adk_session(session_id=str(uuid.uuid4()))
        session_id = session[1]

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        # Prepend instructions to the user prompt to limit access to the specified folder.
        # The access to the folder is guarded by the backend system using access control, but we
        # want to ensure the agent only accesses files in the specified folder.
        # TODO: Build a more robust solution for this.
        pre_prompt = f"ONLY access files in folder with ID: {folder_id}\n\n"

        # Format the user prompt for the agent.
        question_prompt = {
            "role": "user",
            "parts": [
                {
                    "text": pre_prompt + request.question_prompt,
                }
            ],
        }

        # Prepare the POST payload for the ADK server SSE stream.
        payload = {
            "appName": request.agent_name,
            "userId": f"{current_user.id}",
            "sessionId": session_id,
            "newMessage": question_prompt,
        }

        # Start the SSE stream to the ADK server. The server will handle the agent execution
        # and return the results as a stream of events.
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        decoded_chunk = chunk.decode("utf-8")
                        for line in decoded_chunk.splitlines():
                            if line.startswith("data: "):
                                try:
                                    json_data = json.loads(line[len("data: ") :])
                                    yield json.dumps(json_data)
                                except json.JSONDecodeError:
                                    pass
                    yield json.dumps({"type": "complete", "message": "All agents finished."})
        except httpx.HTTPStatusError as e:
            error_message = (
                f"HTTP error during SSE stream: {e.response.status_code} - {e.response.text}"
            )
            yield json.dumps({"type": "error", "message": error_message})
        except httpx.RequestError as e:
            error_message = f"Request error during SSE stream: {e}"
            yield json.dumps({"type": "error", "message": error_message})
        except Exception as e:
            error_message = f"Unexpected error during SSE stream: {e}"
            yield json.dumps({"type": "error", "message": error_message})

    return EventSourceResponse(_run_sse_stream())


@router.post("/{folder_id}/investigations/questions")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
def get_investigative_questions(
    folder_id: int,
    request: schemas.InvestigativeQuestionsRequest,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(get_current_active_user),
) -> List[str]:
    """Generate investigative questions based on the provided goal, context, and files.

    Args:
        folder_id (int): The ID of the folder to limit file access.
        request (schemas.InvestigativeQuestionsRequest): The request containing the goal and context.
        db (Session): The database session.
        current_user (schemas.User): The currently authenticated user.

    Returns:
        List[str]: A list of generated investigative questions.
    """

    def get_folder_contents_as_json():
        """
        Retrieves file metadata for a specific folder.

        Returns:
            A JSON-formatted string representing a list of file dictionaries.
            Returns an empty JSON list '[]' if no files are found.
        """
        # Fetch file objects from the database.
        files_from_db = get_files_from_db(db, folder_id)

        # Use a list comprehension to build the list of file information.
        file_data_list = [
            {
                "filename": file.display_name,
                "mime_type": file.magic_mime,
                "mime_description": file.magic_text,
            }
            for file in files_from_db
        ]

        return json.dumps(file_data_list)

    SYSTEM_INSTRUCTIONS = """
    You are a helpful security engineer that is an expert in digital forensics and reverse engineering.
    I'm investigating a system and need your help analyzing a digital artifact file.
    I have provided the artifacts in this system prompt together with file type, filename.
    * Your sole task is to generate a list of investigative questions based on the provided information.
    * The output MUST be a raw COMMA SEPARATED array of strings.
    * Do NOT include any markdown formatting, code block fences, or extra text.
    """

    # The prompt for the LLM to generate questions.
    PROMPT = f"""
    Based on the provided investigative goal, context, and files, generate a list of investigative questions that could help
    in understanding the system activity.

    The questions must be relevant to the investigation goal and file types/filenames.
    * Generate EXACTLY 5 questions.
    * Each question should be a maximum of 15 words.

    Investigative Goal:
    {request.goal}

    Context:
    {request.context}

    Files:
    {get_folder_contents_as_json()}
    """

    # Get the active LLM provider and model from the configuration.
    active_llm = config.get_active_llms()[0]
    llm_provider = active_llm["name"]
    llm_model = active_llm["config"]["model"]
    provider = manager.LLMManager().get_provider(llm_provider)

    # Initialize the LLM with the specified model and system instructions.
    llm = provider(model_name=llm_model, system_instructions=SYSTEM_INSTRUCTIONS)

    # Generate questions using the LLM.
    questions = llm.generate(prompt=PROMPT)

    # Clean up the output.
    # TODO: Make this more robust and comprehensive.
    questions = questions.replace('"', "").replace("'", "")
    questions = questions.split(",")
    questions = [question.strip() for question in questions if question.strip()]

    return questions
