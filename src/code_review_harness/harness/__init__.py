"""Agent harness primitives: conversation messages, context budget, agent loop."""

from code_review_harness.harness.context import total_chars, truncate_history
from code_review_harness.harness.loop import AgentLoop, AgentResult, MaxTurnsExceeded
from code_review_harness.harness.messages import Message, ToolResult, ToolSpec, ToolUse

__all__ = [
    "AgentLoop",
    "AgentResult",
    "MaxTurnsExceeded",
    "Message",
    "ToolResult",
    "ToolSpec",
    "ToolUse",
    "total_chars",
    "truncate_history",
]
