"""The default tool executor — lookup, validate, run, normalize.

The governance layer wraps this executor to add permission checks and human
approval; the harness loop only knows the :class:`ToolExecutor` protocol.
"""

from __future__ import annotations

from pathlib import Path

from code_review_harness.harness.messages import ToolResult, ToolUse
from code_review_harness.tools.base import ToolExecutionContext, ToolRegistry


class SimpleToolExecutor:
    """Runs a tool use without any governance: resolve, validate, execute."""

    def __init__(self, tool_registry: ToolRegistry, cwd: Path) -> None:
        self._tool_registry = tool_registry
        self._cwd = cwd

    async def execute(self, tool_use: ToolUse) -> ToolResult:
        tool = self._tool_registry.get(tool_use.name)
        if tool is None:
            return ToolResult(
                id=tool_use.id,
                name=tool_use.name,
                output=f"Unknown tool: {tool_use.name}",
                is_error=True,
            )
        try:
            parsed = tool.input_model.model_validate(tool_use.input)
        except Exception as exc:
            return ToolResult(
                id=tool_use.id,
                name=tool_use.name,
                output=f"Invalid input for {tool_use.name}: {exc}",
                is_error=True,
            )
        result = await tool.execute(parsed, ToolExecutionContext(cwd=self._cwd))
        return ToolResult(
            id=tool_use.id,
            name=tool_use.name,
            output=result.output,
            is_error=result.is_error,
        )
