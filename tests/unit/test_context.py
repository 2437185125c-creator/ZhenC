"""Unit tests for the context-budget truncation logic."""
from __future__ import annotations

from code_review_harness.harness.context import total_chars, truncate_history
from code_review_harness.harness.messages import Message, ToolResult


def make_history() -> list[Message]:
    return [
        Message.user("review the repo"),
        Message.assistant(
            "reading file",
            (__import__("code_review_harness.harness.messages", fromlist=["ToolUse"]).ToolUse(
                id="c1", name="read_file", input={"path": "a.py"}
            ),),
        ),
        Message.of_tool_results([ToolResult(id="c1", name="read_file", output="x" * 500)]),
        Message.assistant("final answer"),
    ]


def test_total_chars_counts_text_and_outputs():
    history = make_history()
    assert total_chars(history) > 500


def test_truncate_history_keeps_final_turns_under_budget():
    history = make_history()
    trimmed = truncate_history(history, 200)
    assert total_chars(trimmed) <= 200
    # The latest assistant turn must survive truncation.
    assert trimmed[-1].text == "final answer"
    assert trimmed[-1].role == "assistant"


def test_truncate_replaces_oldest_tool_response_with_placeholder():
    history = make_history()
    trimmed = truncate_history(history, 400)
    placeholder = next(
        (m for m in trimmed if m.is_tool_response and m.tool_results[0].output == "[truncated for context budget]"),
        None,
    )
    assert placeholder is not None


def test_truncate_is_noop_within_budget():
    history = make_history()
    big = total_chars(history) + 1000
    assert truncate_history(history, big) == history
