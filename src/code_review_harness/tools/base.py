"""Tool abstractions.

Tools are the harness's only way to interact with the world.  Each tool
declares a pydantic input model (validated before execution), an ``is_read_only``
flag (used by the governance layer to decide whether a human must approve),
and an async ``execute``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from code_review_harness.harness.messages import ToolSpec


@dataclass
class ToolExecutionContext:
    """Shared state handed to every tool invocation."""

    cwd: Path
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolOutcome:
    """What a tool produced (message-layer concerns like ids are added by the loop)."""

    output: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """Base class for all harness tools."""

    name: str
    description: str
    input_model: type[BaseModel]
    # Declarative flag: tools that never mutate state set this to True and the
    # governance layer lets them run without human approval.
    read_only: bool = False

    @abstractmethod
    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolOutcome:
        """Run the tool with validated arguments."""

    def is_read_only(self, arguments: BaseModel) -> bool:
        """Whether this invocation only reads state (governance uses this)."""
        del arguments
        return self.read_only

    def to_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=self.input_model.model_json_schema(),
        )


class ToolRegistry:
    """Maps tool names to implementations and renders API schemas."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.to_spec() for tool in self._tools.values())
