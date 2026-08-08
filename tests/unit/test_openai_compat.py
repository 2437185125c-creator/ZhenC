"""Unit tests for the OpenAI-compatible provider wire-format conversion."""
from __future__ import annotations

import json

from code_review_harness.harness.messages import Message, ToolResult, ToolUse
from code_review_harness.llm.openai_compat import messages_to_openai, tools_to_openai
from code_review_harness.tools import default_tool_registry


def test_user_message_conversion():
    wire = messages_to_openai((Message.user("hello"),))
    assert wire == [{"role": "user", "content": "hello"}]


def test_assistant_tool_call_conversion():
    use = ToolUse(id="c1", name="read_file", input={"path": "a.py"})
    wire = messages_to_openai((Message.assistant("inspecting", (use,)),))
    assert wire[0]["role"] == "assistant"
    assert wire[0]["tool_calls"][0]["function"]["name"] == "read_file"
    assert json.loads(wire[0]["tool_calls"][0]["function"]["arguments"]) == {"path": "a.py"}


def test_tool_result_conversion():
    result = ToolResult(id="c1", name="read_file", output="content")
    wire = messages_to_openai((Message.tool_result(result),))
    assert wire == [{"role": "tool", "tool_call_id": "c1", "content": "content"}]


def test_tools_conversion_uses_openai_function_format():
    specs = default_tool_registry().specs()
    wire = tools_to_openai(specs)
    assert wire[0]["type"] == "function"
    assert "parameters" in wire[0]["function"]
    names = {t["function"]["name"] for t in wire}
    assert "read_file" in names
