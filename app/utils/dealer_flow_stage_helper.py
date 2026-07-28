"""
dealer_flow_stage_helper.py

Extracts dealer_flow_stage from tool_traces after each stream_response() call
and persists it so the next turn's system prompt knows exactly where in the
dealer flow the user is.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


def update_dealer_flow_stage(
    collected_data: Dict[str, Any],
    tool_traces: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Scans tool_traces (most recent first) for find_dealer_tool results
    and updates collected_data with the latest dealer_flow_stage.

    Args:
        collected_data : current prefill/collected_data dict
        tool_traces    : list of tool_call/tool_result dicts from stream_response()

    Returns:
        Updated copy of collected_data with dealer flow fields set.
    """
    updated = dict(collected_data)

    for trace in reversed(tool_traces):
        if trace.get("type") != "tool_result":
            continue

        tool_name = trace.get("tool_name", "")

        # ── FIX: only skip if tool_name is explicitly set to a NON-dealer tool.
        # If tool_name is "" or None (can happen when name attr is missing on
        # ToolMessage), still inspect the output — don't skip it.
        # This was the bug: `if tool_name and tool_name != "find_dealer_tool"`
        # silently skipped results where tool_name was empty string.
        if tool_name and tool_name != "find_dealer_tool":
            continue

        output = trace.get("output", {})

        if isinstance(output, str):
            try:
                output = json.loads(output)
            except Exception:
                continue

        if not isinstance(output, dict):
            continue

        stage = output.get("dealer_flow_stage")
        if not stage:
            continue

        updated["dealer_flow_stage"] = stage

        if stage == "dealer_selected":
            if "dealer_code" in output:
                updated["last_dealer_code"] = output["dealer_code"]
            if "firm_name" in output:
                updated["last_dealer_name"] = output["firm_name"]

        break  # use only the most recent find_dealer_tool result

    return updated


def reset_dealer_flow_stage(collected_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call this when starting a fresh Upload Purchase flow to clear stale state.
    """
    updated = dict(collected_data)
    updated["dealer_flow_stage"] = ""
    updated.pop("last_dealer_code", None)
    updated.pop("last_dealer_name", None)
    return updated