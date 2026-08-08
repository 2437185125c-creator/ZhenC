"""Context budget — a first-order constraint on the conversation.

Real token accounting is provider-specific, but the harness still needs a
hard cap so a runaway agent cannot balloon the prompt.  We approximate size
with a char budget and, when exceeded, replace the *oldest* tool-response
messages with placeholders — never the most recent assistant/user turns.
"""

from __future__ import annotations

import json

from code_review_harness.harness.messages import Message, ToolResult

TRUNCATED_PLACEHOLDER = "[truncated for context budget]"


def _message_chars(message: Message) -> int:
    text = len(message.text)
    uses = sum(len(json.dumps(use.input, default=str)) for use in message.tool_uses)
    results = sum(len(result.output) for result in message.tool_results)
    return text + uses + results


def total_chars(messages: list[Message]) -> int:
    return sum(_message_chars(m) for m in messages)


def truncate_history(messages: list[Message], budget_chars: int) -> list[Message]:
    """Return a copy of ``messages`` trimmed to fit ``budget_chars``.

    Only tool-response messages are compressed, oldest first; the system and
    latest user/assistant turns are preserved.
    """
    if budget_chars <= 0 or total_chars(messages) <= budget_chars:
        return list(messages)

    result = list(messages)
    while total_chars(result) > budget_chars:
        idx = next((i for i, m in enumerate(result) if m.is_tool_response), None)
        if idx is None:
            break
        original = result[idx]
        result[idx] = Message(
            role="user",
            tool_results=tuple(
                ToolResult(
                    id=r.id,
                    name=r.name,
                    output=TRUNCATED_PLACEHOLDER,
                    is_error=r.is_error,
                )
                for r in original.tool_results
            ),
        )
    return result
