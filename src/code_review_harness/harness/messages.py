"""Core conversation message types shared across the harness.

These models are deliberately provider-agnostic: the agent loop works with
:class:`Message` objects and each ``LLMProvider`` converts them to its own
wire format.  This keeps the harness decoupled from any single vendor API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class ToolUse:
    """A tool invocation requested by the model."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """The outcome of executing a tool invocation."""

    id: str
    name: str
    output: str
    is_error: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """Schema describing a tool exposed to the model."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class Message:
    """A single conversation turn.

    ``role`` is one of ``"system"``, ``"user"`` or ``"assistant"``.  Assistant
    messages may carry tool invocations; user messages may carry the matching
    tool results (mirroring the Anthropic/OpenAI tool-call convention).
    """

    role: str
    text: str = ""
    tool_uses: tuple[ToolUse, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()

    @classmethod
    def user(cls, text: str) -> "Message":
        return cls(role="user", text=text)

    @classmethod
    def assistant(cls, text: str = "", tool_uses: Iterable[ToolUse] = ()) -> "Message":
        return cls(role="assistant", text=text, tool_uses=tuple(tool_uses))

    @classmethod
    def tool_result(cls, result: ToolResult) -> "Message":
        return cls(role="user", text="", tool_results=(result,))

    @classmethod
    def of_tool_results(cls, results: Iterable[ToolResult]) -> "Message":
        return cls(role="user", text="", tool_results=tuple(results))

    @property
    def is_tool_response(self) -> bool:
        """True when this message only carries tool results back to the model."""
        return bool(self.tool_results) and not self.text
