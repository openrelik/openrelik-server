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
from datastores.sql.crud.file import (
    get_file_from_db,
)

SYSTEM_INSTRUCTION = """
I'm security engineer and I'm investigating a system and need your help analyzing a digital artifact file.
I'll provide the artifact in this system prompt together with file type and filename.
* Please respond in a way that is optimal for a chat response.
* Use MAX 100 words in the response.
* Only use information from the file content when asked about the content.
* Allow to elaborate on the content if the user asks for it.

File type:
{magic_text}

Filename:
{filename}

File content:
{content}
"""


def chat_response(llm_provider: str, llm_model: str, file_id: int, prompt: str):
    """Generate a summary for a given file.

    Args:
        llm_provider (str): The name of the LLM provider to use.
        file_id (int): The ID of the file to generate the summary for.
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
            content=file_content, magic_text=file.magic_text, filename=file.display_name
        ),
    )

    # start_time = datetime.now()

    try:
        response = llm.generate(
            prompt=prompt.format(magic_text=file.magic_text, filename=file.display_name)
        )
    # Broad exception handling because we don't know what the AI provider will raise.
    except Exception as e:
        response = f"There was a problem: {e}"

    # end_time = datetime.now()
    # duration = end_time - start_time

    return response
