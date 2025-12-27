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
"""Utility functions for generating formatted reports."""

import hashlib
import string
import textwrap
from enum import IntEnum

from config import config


# TODO: Move to a common location for use by both server and workers.
class Priority(IntEnum):
    """Reporting priority enum to store common values."""

    CRITICAL = 80
    HIGH = 40
    MEDIUM = 20
    LOW = 10
    INFO = 5


def create_workflow_report(
    workflow: object,
    min_priority: int = Priority.HIGH,
    max_priority: int = Priority.CRITICAL,
    include_header: bool = True,
):
    """
    Creates a markdown report string from a completed workflow run.

    Args:
        workflow: The workflow object containing tasks and reports.
        min_priority: Minimum priority level to include in the report.
        max_priority: Maximum priority level to include in the report.
        include_header: Whether to include a header section with workflow info.
    """

    # Convert int parameters to Priority objects if needed
    if isinstance(min_priority, int):
        min_priority = Priority(min_priority)
    if isinstance(max_priority, int):
        max_priority = Priority(max_priority)

    # Define template strings with a placeholder for conditional lines
    # The final template object will be created later inside the loop
    HEADER_TEMPLATE_STR = """
    # OpenRelik: $workflow_name
    ## $workflow_name
    $workflow_url
    """

    TASK_REPORT_TEMPLATE_STR = """
    ## $summary
    * Task: $task_name ($runtime)
    * Priority: $priority_name
    ##### Details
    $markdown
    """

    FILE_REPORT_TEMPLATE_STR = """
    ## $summary
    * Task: $task_name ($runtime)
    * Priority: $priority_name
    * Link to artifact: [$file_name]($file_url)
    {source_file_bullet}
    {original_path_bullet}
    ##### Details
    $markdown
    """

    # Base URL for links
    base_url = config.get("server", {}).get("ui_server_url")

    # Initialize list to hold report sections
    report_sections = []

    has_reports = False

    # Set to track unique file reports to avoid duplicates
    seen_file_reports = set()

    # Handle the header section
    if include_header:
        workflow_url = f"{base_url}/folder/{workflow.folder.id}/"
        header_template = string.Template(textwrap.dedent(HEADER_TEMPLATE_STR).strip())
        header = header_template.substitute(
            workflow_name=workflow.display_name, workflow_url=workflow_url
        )
        report_sections.append(header)

    # Iterate through tasks and their reports
    for task in workflow.tasks:
        task_markdown_content = ""

        if task.task_report and min_priority <= task.task_report.priority <= max_priority:
            has_reports = True
            task_report_template = string.Template(
                textwrap.dedent(TASK_REPORT_TEMPLATE_STR).strip()
            )

            # Determine if summary should be bold based on priority
            priority_level = Priority(task.task_report.priority)
            summary = task.task_report.summary
            if priority_level >= Priority.HIGH:
                summary = f"**{summary}**"

            task_markdown_content += task_report_template.substitute(
                summary=summary,
                task_name=task.display_name,
                runtime=f"{round(task.runtime, 2)}s",
                priority_name=priority_level.name,
                markdown=task.task_report.markdown,
            )

        for file_report in task.file_reports:
            # Create a hash of the attributes to identify unique file reports
            report_data = (
                f"{file_report.file.original_path or ''}"
                f"{file_report.file.hash_sha1 or ''}"
                f"{file_report.file.source_file.id if file_report.file.source_file else ''}"
                f"{file_report.summary or ''}"
                f"{file_report.markdown or ''}"
                f"{file_report.priority or ''}"
            )
            report_hash = hashlib.sha256(report_data.encode()).hexdigest()

            # If we've already seen this exact report, skip it
            if report_hash in seen_file_reports:
                continue

            # Mark this report as seen to filter out duplicates
            seen_file_reports.add(report_hash)

            if min_priority <= file_report.priority <= max_priority:
                has_reports = True
                file_url = f"{base_url}/folder/{workflow.folder.id}/file/{file_report.file.id}"

                # Determine if summary should be bold based on priority
                priority_level = Priority(file_report.priority)
                summary = file_report.summary
                if priority_level >= Priority.HIGH:
                    summary = f"**{summary}**"

                # Conditional bullets
                source_file_bullet = (
                    f"* Extracted from: [{file_report.file.source_file.display_name}]({base_url}/folder/{file_report.file.source_file.folder.id}/file/{file_report.file.source_file.id})"
                    if file_report.file.source_file
                    else ""
                )
                original_path_bullet = (
                    f"* Original path: {file_report.file.original_path}"
                    if file_report.file.original_path
                    else ""
                )

                final_template_str = textwrap.dedent(
                    FILE_REPORT_TEMPLATE_STR.format(
                        source_file_bullet=source_file_bullet,
                        original_path_bullet=original_path_bullet,
                    )
                ).strip()

                # Create the template object
                file_report_template = string.Template(final_template_str)

                task_markdown_content += "\n\n" + file_report_template.substitute(
                    summary=summary,
                    task_name=task.display_name,
                    runtime=f"{round(task.runtime, 2)}s",
                    file_name=file_report.file.display_name,
                    file_url=file_url,
                    priority_name=Priority(file_report.priority).name,
                    markdown=file_report.markdown,
                )

        if task_markdown_content:
            report_sections.append(task_markdown_content)

    if not has_reports:
        report_sections.append(
            f"\nNo reports matching the priority filter were found ({min_priority.name} to {max_priority.name})"
        )

    final_report = "\n".join(report_sections)
    return final_report
