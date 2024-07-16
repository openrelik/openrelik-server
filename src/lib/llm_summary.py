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

from datastores.sql import database
from datastores.sql.crud.file import (
    get_file_from_db,
    get_file_summary_from_db,
    update_file_summary_in_db,
)
from plugins.llm import manager


from . import llm_prompts


def generate_summary(
    llm_provider: str, llm_model: str, file_id: int, file_summary_id: int
):
    """Generate a summary for a given file.

    Args:
        llm_provider (str): The name of the LLM provider to use.
        file_id (int): The ID of the file to generate the summary for.
        file_summary_id (int): The ID of the file summary to update.
    """
    db = database.SessionLocal()
    llm_class = manager.LLMManager().get_provider(llm_provider)
    llm = llm_class(model_name=llm_model)
    file = get_file_from_db(db, file_id)
    file_summary = get_file_summary_from_db(db, file_summary_id)
    prompt = llm_prompts.registry.get(file.data_type)
    MAX_TOKEN_COUNT = 15000

    if not prompt:
        raise RuntimeError(f"No prompt available for this file: {file.data_type}")

    # Rough estimate token count. ~4chars UTF8, 1bytes per char.
    token_count = file.filesize / 4

    # Split the file into chunks
    chunks = []
    encodings_to_try = ["utf-8", "utf-16", "ISO-8859-1"]
    for encoding in encodings_to_try:
        try:
            with open(file.path, "r", encoding=encoding) as fh:
                if token_count > MAX_TOKEN_COUNT:
                    chunk_size_bytes = 10000
                    chunk = ""
                    while True:
                        data = fh.read(chunk_size_bytes)
                        if not data:  # End of file
                            break
                        chunk += data
                        if len(chunk) >= chunk_size_bytes:
                            chunks.append(chunk)
                            chunk = ""  # Reset chunk

                    # Process the remaining chunk (if any)
                    if chunk:
                        chunks.append(chunk)
                else:
                    chunks.append(fh.read())
                break
        except (UnicodeDecodeError, UnicodeError):
            continue

    start_time = datetime.now()
    summaries = []

    num_chunks = 0
    for chunk in chunks:
        num_chunks = num_chunks + 1
        print(f"Processing chunk {num_chunks} / {len(chunks)}")
        triage_prompt = prompt.get("triage")
        max_retries = 5
        current_retry = 0

        while current_retry < max_retries:
            if current_retry > 0:
                print(f"Retrying (attempt {current_retry}/{max_retries})")
            try:
                summary_csv = llm.generate(triage_prompt + chunk)
                summaries.append(summary_csv)
                break
            except:
                current_retry += 1

    summaries_result = "".join(set(summaries))

    print("Generating summary..")
    summary = ""
    summary_prompt = prompt.get("summary")
    max_retries = 10
    current_retry = 0
    while current_retry < max_retries:
        if current_retry > 0:
            print(f"Retrying (attempt {current_retry}/{max_retries})")
        try:
            summary = llm.generate(summary_prompt + summaries_result)
            break
        except:
            current_retry += 1

    end_time = datetime.now()
    duration = end_time - start_time

    file_summary.summary = summary.replace("http", "hXXp")
    file_summary.llm_model_provider = llm.config.get("display_name")
    file_summary.llm_model_name = llm.config.get("model")
    file_summary.llm_model_prompt = prompt.get("triage")
    file_summary.status_short = "complete"
    file_summary.runtime = duration.seconds
    file_summary = update_file_summary_in_db(db, file_summary)

    print(f"Generating summary DONE, duration: {duration.seconds}")
