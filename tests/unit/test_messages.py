"""Unit tests for the harness conversation message model."""
from __future__ import annotations

from code_review_harness.harness.messages import Message, ToolResult, ToolUse


def test_user_message_factory():
    msg = Message.user("hello")
    assert msg.role == "user"
    assert msg.text == "hello"
    assert msg.tool_uses == ()
    assert not msg.is_tool_response


def test_assistant_message_with_tool_uses():
    use = ToolUse(id="call_1", name="read_file", input={"path": "a.py"})
    msg = Message.assistant("checking...", [use])
    assert msg.role == "assistant"
    assert msg.tool_uses == (use,)
    assert not msg.is_tool_response


def test_tool_result_message_is_tool_response():
    result = ToolResult(id="call_1", name="read_file", output="def f(): pass")
    msg = Message.tool_result(result)
    assert msg.role == "user"
    assert msg.is_tool_response
    assert msg.tool_results == (result,)


def test_multiple_tool_results():
    results = [
        ToolResult(id="a", name="read_file", output="x"),
        ToolResult(id="b", name="grep", output="y"),
    ]
    msg = Message.of_tool_results(results)
    assert len(msg.tool_results) == 2
    assert msg.is_tool_response


def test_messages_are_immutable():
    use = ToolUse(id="call_1", name="read_file", input={"path": "a.py"})
    msg = Message.assistant("text", [use])
    try:
        msg.text = "changed"  # type: ignore[misc]
        raise AssertionError("Message should be immutable")
    except AttributeError:
        pass
