"""Unit tests for tool registry and base tool behavior."""
from __future__ import annotations

from pydantic import BaseModel, Field

from code_review_harness.tools.base import BaseTool, ToolExecutionContext, ToolOutcome, ToolRegistry


class _DummyInput(BaseModel):
    path: str = Field(description="a path")


class _ReadOnlyTool(BaseTool):
    name = "dummy_read"
    description = "reads something"
    input_model = _DummyInput

    async def execute(self, arguments, context):
        return ToolOutcome(output=f"read {arguments.path}")

    def is_read_only(self, arguments):
        return True


class _WriteTool(BaseTool):
    name = "dummy_write"
    description = "writes something"
    input_model = _DummyInput

    async def execute(self, arguments, context):
        return ToolOutcome(output=f"wrote {arguments.path}")


def test_registry_register_and_get():
    registry = ToolRegistry()
    tool = _ReadOnlyTool()
    registry.register(tool)
    assert registry.get("dummy_read") is tool
    assert registry.get("nope") is None


def test_registry_specs_include_schema():
    registry = ToolRegistry()
    registry.register(_ReadOnlyTool())
    registry.register(_WriteTool())
    specs = registry.specs()
    assert len(specs) == 2
    by_name = {s.name: s for s in specs}
    assert by_name["dummy_read"].description == "reads something"
    assert by_name["dummy_read"].input_schema["properties"]["path"] is not None


def test_is_read_only_flag():
    assert _ReadOnlyTool().is_read_only(_DummyInput(path="x")) is True
    assert _WriteTool().is_read_only(_DummyInput(path="x")) is False
