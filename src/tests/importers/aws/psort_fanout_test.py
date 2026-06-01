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

import re
from datetime import datetime, timezone

import pytest

from importers.aws.psort_fanout import (
    PSORT_TASK_NAME,
    compute_slice_filters,
    fan_out_psort,
)

_DT_RE = re.compile(r"DATETIME\('([^']+)'\)")


def _psort_node(uuid="psort-uuid"):
    """A psort node with a nested export branch, as a template would carry it."""
    return {
        "type": "task",
        "task_name": PSORT_TASK_NAME,
        "uuid": uuid,
        "task_config": [{"name": "output_format", "value": "jsonl"}],
        "tasks": [
            {
                "type": "task",
                "task_name": "openrelik-worker-export-splunk.tasks.export",
                "uuid": "export-uuid",
                "task_config": [],
                "tasks": [],
            }
        ],
    }


def _spec(psort_node=None):
    """A workflow spec: extraction -> plaso -> psort(->export)."""
    return {
        "workflow": {
            "type": "chain",
            "tasks": [
                {
                    "type": "task",
                    "task_name": "openrelik-worker-plaso.tasks.log2timeline",
                    "uuid": "l2t-uuid",
                    "task_config": [],
                    "tasks": [psort_node or _psort_node()],
                }
            ],
        }
    }


# --- compute_slice_filters -------------------------------------------------


class TestComputeSliceFilters:
    def test_slices_le_1_returns_empty(self):
        now = datetime(2026, 5, 20, tzinfo=timezone.utc)
        assert compute_slice_filters(1, 3, now) == []
        assert compute_slice_filters(0, 3, now) == []

    def test_count_and_shape(self):
        now = datetime(2026, 5, 20, tzinfo=timezone.utc)
        filters = compute_slice_filters(3, 3, now)
        assert len(filters) == 3
        for f in filters:
            assert f.startswith("date > DATETIME('")
            assert "AND date <= DATETIME('" in f

    def test_windows_contiguous_oldest_first_and_end_at_now(self):
        now = datetime(2026, 5, 20, tzinfo=timezone.utc)
        filters = compute_slice_filters(3, 3, now)

        bounds = []
        for f in filters:
            start_s, end_s = _DT_RE.findall(f)
            bounds.append(
                (
                    datetime.strptime(start_s, "%Y-%m-%dT%H:%M:%S"),
                    datetime.strptime(end_s, "%Y-%m-%dT%H:%M:%S"),
                )
            )

        # Oldest first; each start < its end.
        for start, end in bounds:
            assert start < end
        # Each window's end equals the next window's start (no gap/overlap).
        for (_, prev_end), (next_start, _) in zip(bounds, bounds[1:]):
            assert prev_end == next_start
        # Newest window ends at now (naive compare; format drops tzinfo).
        assert bounds[-1][1] == now.replace(tzinfo=None)

    def test_datetime_literals_are_iso8601(self):
        now = datetime(2026, 5, 20, 4, 27, 2, tzinfo=timezone.utc)
        for f in compute_slice_filters(2, 1, now):
            for literal in _DT_RE.findall(f):
                parsed = datetime.strptime(literal, "%Y-%m-%dT%H:%M:%S")
                assert parsed.isoformat(timespec="seconds") == literal


# --- fan_out_psort ---------------------------------------------------------


class TestFanOutPsort:
    def test_empty_filters_is_noop(self):
        spec = _spec()
        before = _spec()
        assert fan_out_psort(spec, []) == before

    def test_no_psort_node_is_noop(self):
        spec = {
            "workflow": {
                "type": "chain",
                "tasks": [
                    {
                        "type": "task",
                        "task_name": "openrelik-worker-extraction.tasks.extract",
                        "uuid": "x",
                        "task_config": [],
                        "tasks": [],
                    }
                ],
            }
        }
        before = {
            "workflow": {
                "type": "chain",
                "tasks": [
                    {
                        "type": "task",
                        "task_name": "openrelik-worker-extraction.tasks.extract",
                        "uuid": "x",
                        "task_config": [],
                        "tasks": [],
                    }
                ],
            }
        }
        assert fan_out_psort(spec, ["date > DATETIME('x')"]) == before

    def test_replaces_psort_with_n_siblings(self):
        spec = _spec()
        filters = ["F1", "F2", "F3"]
        fan_out_psort(spec, filters)

        l2t = spec["workflow"]["tasks"][0]
        siblings = l2t["tasks"]
        assert len(siblings) == 3
        assert all(n["task_name"] == PSORT_TASK_NAME for n in siblings)

    def test_each_sibling_gets_its_filter(self):
        spec = _spec()
        filters = ["F1", "F2", "F3"]
        fan_out_psort(spec, filters)

        siblings = spec["workflow"]["tasks"][0]["tasks"]
        seen = []
        for node in siblings:
            value = next(
                item["value"]
                for item in node["task_config"]
                if item["name"] == "filter"
            )
            seen.append(value)
        assert seen == filters

    def test_each_sibling_keeps_nested_export_branch(self):
        spec = _spec()
        fan_out_psort(spec, ["F1", "F2"])

        for node in spec["workflow"]["tasks"][0]["tasks"]:
            assert len(node["tasks"]) == 1
            assert (
                node["tasks"][0]["task_name"]
                == "openrelik-worker-export-splunk.tasks.export"
            )

    def test_all_uuids_unique_across_clones(self):
        spec = _spec()
        fan_out_psort(spec, ["F1", "F2", "F3"])

        uuids = []

        def _collect(node):
            if isinstance(node, dict):
                if "uuid" in node:
                    uuids.append(node["uuid"])
                for v in node.values():
                    _collect(v)
            elif isinstance(node, list):
                for item in node:
                    _collect(item)

        _collect(spec)
        # psort + export uuids for each of 3 clones (+ l2t) = no duplicates.
        assert len(uuids) == len(set(uuids))

    def test_preserves_existing_task_config_entries(self):
        spec = _spec()
        fan_out_psort(spec, ["F1"])
        node = spec["workflow"]["tasks"][0]["tasks"][0]
        names = {item["name"] for item in node["task_config"]}
        # The original output_format entry survives alongside the new filter.
        assert "output_format" in names
        assert "filter" in names

    def test_existing_datetime_filter_skips_fanout(self):
        """A template psort node that already pins a date window is honored as-is;
        the importer does not fan out over it."""
        node = _psort_node()
        node["task_config"].append(
            {
                "name": "filter",
                "value": "date > DATETIME('2025-01-01T00:00:00')",
            }
        )
        spec = _spec(node)

        fan_out_psort(spec, ["F1", "F2", "F3"])

        # Still a single psort node, filter untouched.
        psort_nodes = spec["workflow"]["tasks"][0]["tasks"]
        assert len(psort_nodes) == 1
        filt = next(
            i["value"] for i in psort_nodes[0]["task_config"] if i["name"] == "filter"
        )
        assert filt == "date > DATETIME('2025-01-01T00:00:00')"

    def test_bare_date_comparison_filter_also_skips_fanout(self):
        """Date constraint without DATETIME() (bare `date >`) is still detected."""
        node = _psort_node()
        node["task_config"].append({"name": "filter", "value": "date > '2025-01-01'"})
        spec = _spec(node)

        fan_out_psort(spec, ["F1", "F2"])

        assert len(spec["workflow"]["tasks"][0]["tasks"]) == 1

    def test_non_date_filter_is_and_combined_with_slice(self):
        """A template predicate like `parser is 'winreg'` is preserved and ANDed
        with each slice's date range."""
        node = _psort_node()
        node["task_config"].append({"name": "filter", "value": "parser is 'winreg'"})
        spec = _spec(node)

        date_filters = [
            "date > DATETIME('2025-01-01T00:00:00') AND date <= DATETIME('2025-04-01T00:00:00')",
            "date > DATETIME('2025-04-01T00:00:00') AND date <= DATETIME('2025-07-01T00:00:00')",
        ]
        fan_out_psort(spec, date_filters)

        psort_nodes = spec["workflow"]["tasks"][0]["tasks"]
        assert len(psort_nodes) == 2
        for node, date_filter in zip(psort_nodes, date_filters):
            value = next(
                i["value"] for i in node["task_config"] if i["name"] == "filter"
            )
            # Template predicate preserved, ANDed with the slice window.
            assert "parser is 'winreg'" in value
            assert date_filter in value
            assert " AND " in value
