# Copyright 2025 Google LLC
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

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from auth.common import websocket_get_current_active_user
from config import get_active_llms
from datastores.sql.crud.authz import require_access
from datastores.sql.crud.file import (
    create_file_chat_in_db,
    create_file_chat_message_in_db,
    get_latest_file_chat_from_db,
)
from datastores.sql.database import get_db_connection
from datastores.sql.models.role import Role
from lib.llm_file_chat import BASE_SYSTEM_INSTRUCTIONS, create_chat_session

from . import schemas

router = APIRouter()


@router.websocket("/files/{file_id}/chat")
@require_access(allowed_roles=[Role.VIEWER, Role.EDITOR, Role.OWNER])
async def websocket_endpoint(
    file_id: str,
    websocket: WebSocket,
    db: Session = Depends(get_db_connection),
    current_user: schemas.User = Depends(websocket_get_current_active_user),
):
    """
    WebSocket endpoint for chatting with a file using an LLM.
    """

    # Try to get the latest file chat for the current user
    file_chat = get_latest_file_chat_from_db(
        db=db,
        file_id=file_id,
        user_id=current_user.id,
    )

    # Create a new file chat
    if not file_chat:
        file_chat_schema = schemas.FileChatCreate(
            system_instructions=BASE_SYSTEM_INSTRUCTIONS,
            user_id=current_user.id,
            file_id=file_id,
        )
        file_chat = create_file_chat_in_db(db=db, file_chat=file_chat_schema)

    # Get the file chat history for the current user
    history = file_chat.get_chat_history()

    active_llm = get_active_llms()[0]
    llm_provider = active_llm["name"]
    llm_model = active_llm["config"]["model"]
    chat_session = create_chat_session(llm_provider, llm_model, file_id, history)

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            start_time = datetime.now()
            response = chat_session.chat(data)
            # Create a new file chat message
            end_time = datetime.now()
            duration = end_time - start_time
            file_chat_message = schemas.FileChatMessageCreate(
                file_chat_id=file_chat.id,
                request_prompt=data,
                response_text=response,
                runtime=duration.seconds,
            )
            create_file_chat_message_in_db(db=db, file_chat_message=file_chat_message)
            await websocket.send_text(response)
    except WebSocketDisconnect:
        # FastAPI will automatically close the connection
        pass
