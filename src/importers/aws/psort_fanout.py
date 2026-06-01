# Copyright 2026 Google LLC
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
"""Expand a single psort task node into N filtered siblings in a workflow spec.

The plaso psort worker is slice-agnostic: it runs once and accepts an opaque
``filter`` task_config value that it passes verbatim to ``psort.py``. Producing
N time-sliced outputs is therefore the workflow creator's job — it duplicates
the psort node once per filter, so the workflow engine runs them as a parallel
Celery group, each followed by its own (already-nested) export branch.

``compute_slice_filters`` is the only time-slice-specific piece (it builds
``DATETIME`` range filters). ``fan_out_psort`` is filter-agnostic: it clones the
psort subtree once per supplied filter string, whatever those strings express.
"""

import copy
import logging
import re
from datetime import datetime

from dateutil.relativedelta import relativedelta

from lib.workflow_utils import replace_uuids

logger = logging.getLogger(__name__)

# Detects whether a psort filter already constrains the event date — either via
# the DATETIME() helper or a bare `date`/`timestamp` comparison. When the
# template's psort node already carries such a filter, the importer honors it
# and does not fan out (the author pinned an explicit window).
_DATE_FILTER_RE = re.compile(r"\bDATETIME\s*\(|\b(?:date|timestamp)\b\s*[<>=]", re.I)


def _is_date_filter(filter_expr: str) -> bool:
    """True if ``filter_expr`` already constrains the event date/time."""
    return bool(_DATE_FILTER_RE.search(filter_expr or ""))

PSORT_TASK_NAME = "openrelik-worker-plaso.tasks.psort"

# ISO 8601 (second precision) — accepted by plaso's DATETIME() filter helper.
_FILTER_DT_FMT = "%Y-%m-%dT%H:%M:%S"


def compute_slice_filters(
    slices: int, months_per_slice: int, now: datetime
) -> list[str]:
    """Build psort event-filter expressions for N trailing time windows.

    Slice i (1-based, newest last) covers the half-open interval
    ``(now - i*M months, now - (i-1)*M months]`` so adjacent windows abut with
    no overlap and no gap, and the newest window ends at ``now``.

    Args:
        slices: Number of time windows. ``<= 1`` returns an empty list (no
            fan-out — a single unfiltered psort run).
        months_per_slice: Width of each window in months.
        now: The anchor time (the newest window's end). Pass an explicit value
            so the windows are pinned at workflow-creation time.

    Returns:
        A list of ``date > DATETIME('…') AND date <= DATETIME('…')`` strings,
        oldest window first. Empty when ``slices <= 1``.
    """
    if slices <= 1:
        return []
    filters = []
    for i in range(slices, 0, -1):
        start = now - relativedelta(months=i * months_per_slice)
        end = now - relativedelta(months=(i - 1) * months_per_slice)
        filters.append(
            f"date > DATETIME('{start.strftime(_FILTER_DT_FMT)}') "
            f"AND date <= DATETIME('{end.strftime(_FILTER_DT_FMT)}')"
        )
    return filters


def _get_filter(node: dict) -> str:
    """Return the psort node's current ``filter`` task_config value, or ""."""
    for item in node.get("task_config", []) or []:
        if item.get("name") == "filter":
            return (item.get("value") or "").strip()
    return ""


def _combine_filters(existing: str, added: str) -> str:
    """AND-combine two psort filter expressions.

    When the node already carries a (non-date) filter such as
    ``parser is 'winreg'``, the slice's date-range filter is ANDed with it
    rather than replacing it, so a sliced run still honors the template's
    predicate. Each side is parenthesized to keep precedence unambiguous.
    """
    existing = (existing or "").strip()
    added = (added or "").strip()
    if not existing:
        return added
    if not added:
        return existing
    return f"({existing}) AND ({added})"


def _set_filter(node: dict, filter_expr: str) -> None:
    """AND-combine ``filter_expr`` into a psort node's ``task_config`` in place.

    If a ``filter`` entry already exists, its value is ANDed with ``filter_expr``
    (see ``_combine_filters``) so a template-supplied predicate survives slicing;
    otherwise a new ``filter`` entry is appended.
    """
    task_config = node.setdefault("task_config", [])
    for item in task_config:
        if item.get("name") == "filter":
            item["value"] = _combine_filters(item.get("value", ""), filter_expr)
            return
    task_config.append({"name": "filter", "value": filter_expr})


def _find_psort_parent(node, parent_list=None):
    """Locate the first psort node and the list it lives in.

    Walks the spec tree (the same nested ``{"type", "task_name", "tasks": [...]}``
    shape consumed by ``create_workflow_signature``). Returns a
    ``(parent_list, index)`` pair locating the psort node within its containing
    ``tasks`` list, or ``None`` if no psort node exists.
    """
    if isinstance(node, dict):
        if parent_list is None and node.get("task_name") == PSORT_TASK_NAME:
            # The top-level node itself is psort and has no containing list.
            return None
        for key in ("workflow", "callback"):
            if key in node:
                found = _find_psort_parent(node[key], None)
                if found:
                    return found
        tasks = node.get("tasks")
        if isinstance(tasks, list):
            for idx, child in enumerate(tasks):
                if isinstance(child, dict) and child.get("task_name") == PSORT_TASK_NAME:
                    return tasks, idx
                found = _find_psort_parent(child, tasks)
                if found:
                    return found
    return None


def _should_export(export_slices: str, slice_idx: int, total: int) -> bool:
    """Decide whether the clone at ``slice_idx`` keeps its downstream branch.

    Clones are ordered oldest window first, so ``slice_idx == total - 1`` is the
    newest slice.

    Args:
        export_slices: Selection mode — ``"all"`` (every clone exports),
            ``"latest"`` (only the newest), or a 1-based slice number as a
            string (e.g. ``"2"`` = the 2nd-oldest slice only). Unrecognized
            values fall back to ``"all"`` (logged) so a config typo never
            silently drops every export.
        slice_idx: Zero-based index of this clone in oldest-first order.
        total: Total number of clones.

    Returns:
        True if this clone should keep its export branch.
    """
    mode = (export_slices or "all").strip().lower()
    if mode == "all":
        return True
    if mode == "latest":
        return slice_idx == total - 1
    try:
        wanted = int(mode)  # 1-based slice number
    except ValueError:
        logger.warning(
            "fan_out_psort: unrecognized export_slices=%r; exporting all slices",
            export_slices,
        )
        return True
    return slice_idx == wanted - 1


def fan_out_psort(
    spec: dict, filters: list[str], export_slices: str = "all"
) -> dict:
    """Replace the psort node in ``spec`` with one clone per filter, in place.

    Each clone is a deep copy of the entire psort subtree — including any nested
    export branch under its ``tasks`` — with the given filter injected into its
    ``task_config`` and fresh UUIDs assigned (so each becomes its own tracked
    Task and Celery task_id rather than colliding with its siblings). If the
    template's psort node already carries a non-date filter (e.g.
    ``parser is 'winreg'``), each slice's date range is ANDed onto it so the
    predicate is preserved.

    Filter-agnostic: ``filters`` may be DATETIME ranges (time slices) or any
    other psort filter expression.

    No-ops (returns ``spec`` unchanged) when:
      * ``filters`` is empty (caller wants a single unfiltered run),
      * no psort node is found (logged), or
      * the template's psort node already has its own date/time filter — the
        author pinned an explicit window, so the importer honors it instead of
        fanning out (logged).

    Slice selection for export: every clone runs psort and registers its output
    in OpenRelik, but only the clones chosen by ``export_slices`` keep the
    template's downstream branch (e.g. an export-to-Splunk/S3 task nested under
    the psort node's ``tasks``). Non-selected clones have their ``tasks`` removed
    so they are processed but not exported. Has no effect if the psort node has
    no nested ``tasks`` to begin with.

    Args:
        spec: The workflow spec dict (as parsed from ``workflow.spec_json``).
        filters: Opaque psort filter strings, one per desired psort clone,
            ordered oldest window first (as ``compute_slice_filters`` emits).
        export_slices: Which clones keep their export branch — ``"all"``
            (default), ``"latest"`` (newest slice only), or a 1-based slice
            number as a string (e.g. ``"2"``). See ``_should_export``.

    Returns:
        The same ``spec`` dict, mutated in place.
    """
    if not filters:
        return spec

    located = _find_psort_parent(spec, None)
    if not located:
        logger.warning(
            "fan_out_psort: no %s node found in spec; leaving unchanged",
            PSORT_TASK_NAME,
        )
        return spec

    parent_list, idx = located
    template_node = parent_list[idx]

    # If the template already pins a date/time window, honor it: don't fan out.
    existing_filter = _get_filter(template_node)
    if _is_date_filter(existing_filter):
        logger.info(
            "fan_out_psort: psort node already has a date filter (%r); "
            "honoring it and skipping fan-out",
            existing_filter,
        )
        return spec

    total = len(filters)
    clones = []
    for slice_idx, filter_expr in enumerate(filters):
        clone = copy.deepcopy(template_node)
        _set_filter(clone, filter_expr)
        # Drop the downstream (export) branch on slices we don't want exported;
        # the clone still runs psort and registers its output.
        if not _should_export(export_slices, slice_idx, total):
            clone["tasks"] = []
        # Each clone needs unique identifiers: the source node was already
        # UUID-stamped by create_workflow, so copies would otherwise share its
        # UUIDs, which key the Task rows and Celery task_ids.
        replace_uuids(clone)
        clones.append(clone)

    parent_list[idx : idx + 1] = clones
    return spec
