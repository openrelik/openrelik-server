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


from openrelik_ai_common.providers import manager

from datastores.sql import database
from datastores.sql.crud.file import get_file_from_db

BASE_SYSTEM_INSTRUCTIONS = """
You are a helpful security engineer that is an expert in digital forensics and reverse engineering.
I'm investigating a system and need your help analyzing a digital artifact file.
I have provided the artifact in this system prompt together with file type, filename
* If available, I have also provided an AI generated summary of the file focusing on security issues.
* If available, I have also provided our previous conversation history.
* Please respond in a way that is optimal for a chat response.
* Use MAX 100 words in the response.
* ONLY USE information from the file content or your previous responses when asked about the content.
* Elaborate on the content if the user asks for it.
* DO NOT answer any other questions that is NOT PRESENT in the file content OR your previous responses.
"""

SYSTEM_INSTRUCTION = """
{base_system_instructions}

File type:
{magic_text}

Filename:
{filename}

AI generated summary of the file focusing on security issues:
{summary}

File content:
{content}

Our previous conversation history:
{history}
"""


def create_chat_session(
    llm_provider: str, llm_model: str, file_id: int, history: str | None = None
):
    """Generate a summary for a given file.

    Args:
        llm_provider (str): The name of the LLM provider to use.
        file_id (int): The ID of the file to start the chat session for.
        history (str): The chat history to include.

    Returns:
        LLM: The LLM instance for the chat session.
    """
    db = database.SessionLocal()
    file = get_file_from_db(db, file_id)

    encodings_to_try = ["utf-8", "utf-16", "ISO-8859-1"]
    for encoding in encodings_to_try:
        try:
            with open(file.path, "r", encoding=encoding) as fh:
                file_content = fh.read()
                break
        except (UnicodeDecodeError, UnicodeError):
            continue

    provider = manager.LLMManager().get_provider(llm_provider)
    llm = provider(
        model_name=llm_model,
        system_instructions=SYSTEM_INSTRUCTION.format(
            base_system_instructions=BASE_SYSTEM_INSTRUCTIONS,
            content=file_content,
            magic_text=file.magic_text,
            filename=file.display_name,
            summary=file.summaries[0].summary if file.summaries else "No summary available",
            history=history,
        ),
    )
    return llm
