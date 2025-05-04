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

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from auth.common import websocket_get_current_active_user
from config import get_active_llms
from datastores.sql.crud.authz import require_access
from datastores.sql.database import get_db_connection
from datastores.sql.models.role import Role
from lib.llm_file_chat import create_chat_session

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
    active_llm = get_active_llms()[0]
    llm_provider = active_llm["name"]
    llm_model = active_llm["config"]["model"]
    llm = create_chat_session(llm_provider, llm_model, file_id)
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            response = llm.chat(data)
            await websocket.send_text(response)
    except WebSocketDisconnect:
        # FastAPI will automatically close the connection
        pass
