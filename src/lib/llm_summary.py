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

from datetime import datetime

from openrelik_ai_common.providers import manager

from datastores.sql import database
from datastores.sql.crud.file import (
    get_file_from_db,
    get_file_summary_from_db,
    update_file_summary_in_db,
)

SYSTEM_INSTRUCTION = """
I'm security engineer and I'm investigating a system and need your help analyzing a digital artifact file.
I'll provide the artifact separately. Focus on identifying any **interesting content** within the file that
could be relevant to understanding system activity. This could include:

* **System Configuration:** Settings that reveal how the system is configured (e.g., firewall rules, scheduled tasks).
* **Application Data:** Information about installed software and its usage (e.g., software logs, user preferences).
* **User Activity:**  Entries that indicate user actions on the system (e.g., login attempts, file modifications).

**IMPORTANT** Your response should focus on **describing the content** and its potential implications for
security. If the content is unremarkable, respond with "No significant findings observed".
"""

ANALYSIS_PROMPT = """
**File Context:**
* **Filename:** {filename}
* **File type:** {magic_text}

Please analyze this file and provide a summary of its content. For each significant finding, briefly describe:

* **What:**  What the content represents within the file (e.g., system configuration setting, user activity log entry).
* **Context:** How the content might be relevant to understanding system activity (e.g., indicates a user logged in remotely, defines a scheduled backup).

* **Keep the summary short and concise and don NOT repeat yourself.

**Examples of Findings:**
* **Bash History:** Contains commands related to system administration tasks (e.g., installing software, modifying configurations).
* **SSH Logs:** Records successful and failed login attempts with timestamps and IP addresses.
* **Web Server Logs:** Shows requests made to the web server, including user-agent information and accessed URLs.
* **Sudoers File:** Defines user privileges for elevated commands.
* **Apache Config:**  Specifies configuration settings for the Apache web server.
* **Scheduled Tasks:** Lists automated tasks configured to run at specific times or triggers.
* **Firewall Config:**  Defines rules for allowing or blocking network traffic.
* **Application Logs:** Records activities performed by a specific application.
"""

SUMMARY_PROMPT = """
Please summarize all security findings using max 4 paragraphs with 50 words each. Keep the summary concise and don't describe the summary.
Format: Markdown with clear subtitles.

**Findings:**
{analysis_details}
"""


def generate_summary(llm_provider: str, llm_model: str, file_id: int, file_summary_id: int):
    """Generate a summary for a given file.

    Args:
        llm_provider (str): The name of the LLM provider to use.
        file_id (int): The ID of the file to generate the summary for.
        file_summary_id (int): The ID of the file summary to update.
    """
    db = database.SessionLocal()
    provider = manager.LLMManager().get_provider(llm_provider)
    llm = provider(model_name=llm_model, system_instructions=SYSTEM_INSTRUCTION)
    file = get_file_from_db(db, file_id)
    file_summary = get_file_summary_from_db(db, file_summary_id)

    encodings_to_try = ["utf-8", "utf-16", "ISO-8859-1"]
    for encoding in encodings_to_try:
        try:
            with open(file.path, "r", encoding=encoding) as fh:
                file_content = fh.read()
                break
        except (UnicodeDecodeError, UnicodeError):
            continue

    start_time = datetime.now()

    try:
        details = llm.generate_file_analysis(
            prompt=ANALYSIS_PROMPT.format(magic_text=file.magic_text, filename=file.display_name),
            file_content=file_content,
        )
        summary = llm.generate(prompt=SUMMARY_PROMPT.format(analysis_details=details))
    # Broad exception handling because we don't know what the AI provider will raise.
    except Exception as e:
        summary = f"There was a problem with the analysis: {e}"

    end_time = datetime.now()
    duration = end_time - start_time

    file_summary.summary = summary.replace("http", "hXXp")
    file_summary.llm_model_provider = llm.DISPLAY_NAME
    file_summary.llm_model_name = llm.config.get("model")
    file_summary.llm_model_prompt = f"{SYSTEM_INSTRUCTION}\n\n{ANALYSIS_PROMPT}"
    file_summary.status_short = "complete"
    file_summary.runtime = duration.seconds
    file_summary = update_file_summary_in_db(db, file_summary)
