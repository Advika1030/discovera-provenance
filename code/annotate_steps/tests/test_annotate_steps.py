"""Tests for --annotate-steps. No network.  Run: .venv/bin/python -m pytest tests/test_annotate_steps.py -q"""

import asyncio
import inspect
import json
import os
import sys

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool, ToolException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import batch_runner_single as runner  # noqa: E402
from annotate_steps import annotated_schema, classify_status, timeline_markdown, wrap_tools  # noqa: E402

OUTPUT = json.dumps({"rows": [{"Gene": "CTNNB1"}], "total_rows": 1})


def fake_tool(name="csv_read", output=OUTPUT, fail=False, schema=None):
    seen = []

    async def call(**kwargs):
        seen.append(kwargs)
        if fail:
            raise ToolException("GraphQL request failed: 504")
        return output, None

    tool = StructuredTool(
        name=name,
        description="fake description",
        coroutine=call,
        response_format="content_and_artifact",
        args_schema=schema or {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    )
    return tool, seen


def invoke(tool, args):
    return asyncio.run(tool.ainvoke({"name": tool.name, "args": args, "id": "call_1", "type": "tool_call"}))


def test_schema_requires_description_first_and_keeps_fields():
    tool, _ = fake_tool()
    schema = annotated_schema(tool)
    assert list(schema["properties"]) == ["step_description", "id"]
    assert schema["required"] == ["step_description", "id"]
    assert "$ref" not in json.dumps(schema)
    assert "step_description" not in tool.args_schema["properties"]  # original untouched


def test_csv_filter_conditions_get_real_fields():
    flattened = {"type": "object", "required": ["csv_id"], "properties": {
        "csv_id": {"type": "string"},
        "conditions": {"anyOf": [{"type": "array", "items": {"type": "object", "additionalProperties": True}},
                                 {"type": "null"}]}}}
    tool, _ = fake_tool("csv_filter", schema=flattened)
    schema = annotated_schema(tool)
    items = schema["properties"]["conditions"]["anyOf"][0]["items"]
    assert set(items["properties"]) == {"column", "op", "value"}
    assert "$ref" not in json.dumps(schema)


def test_description_is_stripped_and_output_unchanged():
    tool, seen = fake_tool()
    steps = []
    [wrapped] = wrap_tools([tool], steps)
    assert (wrapped.name, wrapped.description) == (tool.name, tool.description)
    msg = invoke(wrapped, {"step_description": "Read the protein table.", "id": "a"})
    assert isinstance(msg, ToolMessage) and msg.content == OUTPUT
    assert seen == [{"id": "a"}]
    assert steps == [{"step": 1, "tool": "csv_read", "args": {"id": "a"},
                      "step_description": "Read the protein table.",
                      "description_missing": False, "status": "ok"}]


@pytest.mark.parametrize("args", [{"id": "a"}, {"id": "a", "step_description": "   "}, {"id": "a", "step_description": None}])
def test_missing_or_blank_description_still_runs(args):
    tool, seen = fake_tool()
    steps = []
    [wrapped] = wrap_tools([tool], steps)
    assert invoke(wrapped, args).content == OUTPUT
    assert seen == [{"id": "a"}]
    assert steps[0]["step_description"] is None and steps[0]["description_missing"] is True


@pytest.mark.parametrize(
    "output, status",
    [
        (OUTPUT, "ok"),
        ("plain text answer", "ok"),
        ('{"rows": [], "total_rows": 0}', "empty"),
        ('{"results": []}', "empty"),
        ("[]", "empty"),
        ('{"error": {"message": "bad"}}', "error"),
        ('{"status_code": 504}', "error"),
        ("Error: something failed", "error"),
        ("GraphQL request failed: 504", "error"),
    ],
)
def test_status_detection(output, status):
    assert classify_status(output) == status


def test_tool_exception_is_recorded_and_reraised():
    tool, _ = fake_tool(fail=True)
    steps = []
    [wrapped] = wrap_tools([tool], steps)
    with pytest.raises(ToolException, match="504"):
        asyncio.run(wrapped.ainvoke({"step_description": "Search.", "id": "a"}))
    assert steps[0]["status"] == "error"


def run_flag(monkeypatch, annotate):
    """Run run_once with a fake tool and agent; return (tools given to the agent, its system prompt)."""
    tool, _ = fake_tool()
    captured = {}

    def fake_agent(model, tools, **kwargs):
        captured["tools"] = tools
        return object()

    async def fake_stream(agent, inputs):
        captured["system"] = inputs["messages"][0].content
        return "report", [], [], []

    monkeypatch.setattr(runner, "_load_mcp_tools", lambda url: [tool])
    monkeypatch.setattr(runner, "create_react_agent", fake_agent)
    monkeypatch.setattr(runner, "_astream_updates", fake_stream)
    result = runner.run_once("ctx", "prompt", "Discovera", "http://x", object(), [], annotate_steps=annotate)
    return tool, captured, result


def test_flag_off_tools_not_wrapped(monkeypatch):
    tool, captured, result = run_flag(monkeypatch, False)
    assert captured["tools"] == [tool]
    assert captured["system"] == runner.SERVER_INSTRUCTIONS
    assert "annotated_steps" not in result
    assert inspect.signature(runner.run_once).parameters["annotate_steps"].default is False


def test_flag_on_tools_wrapped_and_prompt_added(monkeypatch):
    tool, captured, result = run_flag(monkeypatch, True)
    assert captured["tools"][0] is not tool
    assert "step_description" in captured["tools"][0].args_schema["properties"]
    assert captured["system"].startswith(runner.SERVER_INSTRUCTIONS)
    assert captured["system"].endswith(
        "Every tool call must include step_description. Do not send text-only messages before your final report."
    )
    assert result["annotated_steps"] == []


def test_timeline_table():
    md = timeline_markdown("1", [
        {"step": 1, "tool": "csv_read", "step_description": "Read a | b.", "status": "ok"},
        {"step": 2, "tool": "gsea_pipe", "step_description": None, "status": "error"},
    ])
    assert "| step | tool | step_description | status |" in md
    assert "| 1 | csv_read | Read a \\| b. | ok |" in md
    assert "| 2 | gsea_pipe | (missing) | error |" in md
