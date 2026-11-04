"""
--annotate-steps: the agent attaches one plain-English sentence to every tool call.

Each MCP tool is wrapped in a StructuredTool with the same name and description and one
extra required field, step_description. The wrapper removes that field, forwards the
other arguments to the original tool unchanged, returns its output unchanged, and records
the call. The sentence is the agent's own account of the step, not proof of why it acted.
"""

import copy
import json
import re
from typing import Any, Dict, List

from langchain_core.tools import StructuredTool

ANNOTATE_INSTRUCTIONS = (
    "\n\nEvery tool call must include step_description. "
    "Do not send text-only messages before your final report."
)

STEP_DESCRIPTION_SCHEMA = {
    "type": "string",
    "description": (
        "One plain-English sentence saying what this step does and why, e.g. 'Filter the "
        "protein table to significant proteins (FDR < 0.05) to build a gene list for "
        "enrichment.' Use readable names for tables, not csv_ids."
    ),
}

# Mirrors CsvFilterCondition in discovera/src/discovera_fastmcp/pydantic.py. The MCP ->
# LangChain conversion delivers these items as a bare object with no fields.
CSV_FILTER_CONDITION_SCHEMA = {
    "type": "object",
    "properties": {
        "column": {"type": "string", "description": "Column to filter on."},
        "op": {
            "type": "string",
            "description": (
                "Operator: one of ==, !=, >, >=, <, <=, in, not_in, contains, not_contains, "
                "startswith, endswith, isnull, notnull."
            ),
        },
        "value": {"description": "Right-hand value for comparison; for in/not_in provide list."},
    },
    "required": ["column", "op"],
}

HTTP_ERROR_RE = re.compile(
    r"\b(?:http(?: error)?|status(?: code)?|request failed:?)\s*[45]\d\d\b", re.IGNORECASE
)


def annotated_schema(tool: Any) -> Dict[str, Any]:
    """The tool's schema with step_description required and listed first."""
    schema = copy.deepcopy(tool.args_schema)
    properties = schema.get("properties", {})
    if tool.name == "csv_filter" and "conditions" in properties:
        conditions = properties["conditions"]
        for variant in conditions.get("anyOf", [conditions]):
            if variant.get("type") == "array":
                variant["items"] = copy.deepcopy(CSV_FILTER_CONDITION_SCHEMA)
    schema["properties"] = {"step_description": copy.deepcopy(STEP_DESCRIPTION_SCHEMA), **properties}
    schema["required"] = ["step_description"] + list(schema.get("required", []))
    return schema


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in content
        )
    return "" if content is None else str(content)


def classify_status(content: Any) -> str:
    """error = "error" key or HTTP error in the output; empty = no rows or results; else ok."""
    text = _text(content).strip()
    try:
        payload = json.loads(text)
    except ValueError:
        payload = text
    if isinstance(payload, dict):
        if payload.get("error"):
            return "error"
        for key in ("status_code", "status"):
            if isinstance(payload.get(key), int) and payload[key] >= 400:
                return "error"
        if payload.get("total_rows") == 0 or payload.get("results") == []:
            return "empty"
    elif isinstance(payload, str):
        if payload.lower().startswith("error") or HTTP_ERROR_RE.search(payload):
            return "error"
    if payload in ([], {}, ""):
        return "empty"
    return "ok"


def wrap_tools(tools: List[Any], steps: List[Dict[str, Any]]) -> List[StructuredTool]:
    """Wrap every tool; each call appends its record to `steps`."""

    def make(tool: Any) -> StructuredTool:
        async def run(**kwargs: Any) -> Any:
            description = kwargs.pop("step_description", None)
            missing = not isinstance(description, str) or not description.strip()
            # Numbered and stored here so calls made in one message keep their order.
            record = {
                "step": len(steps) + 1,
                "tool": tool.name,
                "args": kwargs,
                "step_description": None if missing else description,
                "description_missing": missing,
                "status": "error",
            }
            steps.append(record)
            result = await tool.coroutine(**kwargs)  # an exception leaves status "error"
            content = result[0] if isinstance(result, tuple) else result
            record["status"] = classify_status(content)
            return result

        return StructuredTool(
            name=tool.name,
            description=tool.description,
            args_schema=annotated_schema(tool),
            coroutine=run,
            response_format=tool.response_format,
            metadata=tool.metadata,
        )

    return [make(t) for t in tools]


def timeline_markdown(task_id: str, steps: List[Dict[str, Any]]) -> str:
    rows = [f"# Task {task_id}: timeline", "", "| step | tool | step_description | status |", "|---|---|---|---|"]
    for s in steps:
        text = s["step_description"] if s["step_description"] is not None else "(missing)"
        text = " ".join(text.split()).replace("|", "\\|")
        rows.append(f"| {s['step']} | {s['tool']} | {text} | {s['status']} |")
    return "\n".join(rows) + "\n"
