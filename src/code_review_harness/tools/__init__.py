"""Tool registry and built-in tools.

This module owns the *composition* of the default tool set; each tool lives in
its own module (``file_tools``, ``git_tools``, ...) to keep the coupling small.
"""

from __future__ import annotations

from code_review_harness.tools.base import BaseTool, ToolExecutionContext, ToolOutcome, ToolRegistry
from code_review_harness.tools.check_tools import RunChecksTool
from code_review_harness.tools.executor import SimpleToolExecutor
from code_review_harness.tools.file_tools import GrepTool, ReadFileTool, WriteFileTool
from code_review_harness.tools.git_tools import GitDiffTool, GitStatusTool

_READ_ONLY_TOOLS = (
    ReadFileTool(),
    GrepTool(),
    GitDiffTool(),
    GitStatusTool(),
)


def default_tool_registry() -> ToolRegistry:
    """Return a registry pre-loaded with the built-in read-only tools (review stage)."""
    registry = ToolRegistry()
    for tool in _READ_ONLY_TOOLS:
        registry.register(tool)
    return registry


def fix_tool_registry() -> ToolRegistry:
    """Return a registry with read-only tools plus write_file and run_checks (fix stage)."""
    registry = default_tool_registry()
    registry.register(WriteFileTool())
    registry.register(RunChecksTool())
    return registry


__all__ = [
    "BaseTool",
    "SimpleToolExecutor",
    "ToolExecutionContext",
    "ToolOutcome",
    "ToolRegistry",
    "default_tool_registry",
    "fix_tool_registry",
]
