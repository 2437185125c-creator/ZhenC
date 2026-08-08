"""Tests for the governed tool executor (permission + approval wiring)."""
from __future__ import annotations

from pathlib import Path

import pytest

from code_review_harness.governance.approval import auto_approve, auto_deny
from code_review_harness.governance.executor import GovernedToolExecutor
from code_review_harness.governance.modes import PermissionMode
from code_review_harness.governance.permissions import PermissionChecker
from code_review_harness.harness.messages import ToolUse
from code_review_harness.tools import default_tool_registry


def make_executor(tmp_path, *, checker=None, approval=None, event_sink=None):
    registry = default_tool_registry()
    return GovernedToolExecutor(
        tool_registry=registry,
        checker=checker or PermissionChecker(mode=PermissionMode.DEFAULT),
        cwd=Path(tmp_path),
        approval_gate=approval or auto_deny,
        event_sink=event_sink,
    )


@pytest.mark.asyncio
async def test_read_only_runs_without_approval(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    executor = make_executor(tmp_path, approval=auto_deny)
    result = await executor.execute(
        ToolUse(id="c1", name="read_file", input={"path": "app.py"})
    )
    assert not result.is_error
    assert "x = 1" in result.output


@pytest.mark.asyncio
async def test_mutating_denied_when_user_says_no(tmp_path):
    # With an always-deny gate, the mutating call must be blocked in default mode.
    executor = make_executor(tmp_path, approval=auto_deny)
    result = await executor.execute(
        ToolUse(id="c2", name="write_file", input={"path": "app.py", "content": "boom"})
    )
    # write_file is not registered, so it is an unknown tool error.
    assert result.is_error


@pytest.mark.asyncio
async def test_approval_gate_is_called_for_mutating_tool(tmp_path):
    calls: list[tuple[str, str]] = []

    async def tracking_gate(tool_name: str, reason: str) -> bool:
        calls.append((tool_name, reason))
        return True

    # Register a fake mutating tool so the gate actually gets exercised.
    from pydantic import BaseModel

    from code_review_harness.tools.base import BaseTool, ToolOutcome

    class _WriteInput(BaseModel):
        path: str
        content: str

    class _FakeWrite(BaseTool):
        name = "fake_write"
        description = "mutates a file"
        input_model = _WriteInput

        async def execute(self, arguments, context):
            (context.cwd / arguments.path).write_text(arguments.content, encoding="utf-8")
            return ToolOutcome(output="written")

    registry = default_tool_registry()
    registry.register(_FakeWrite())
    checker = PermissionChecker(mode=PermissionMode.DEFAULT)
    executor = GovernedToolExecutor(
        tool_registry=registry,
        checker=checker,
        cwd=Path(tmp_path),
        approval_gate=tracking_gate,
    )

    result = await executor.execute(
        ToolUse(id="c3", name="fake_write", input={"path": "app.py", "content": "new"})
    )

    assert not result.is_error
    assert len(calls) == 1
    assert calls[0][0] == "fake_write"
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "new"


@pytest.mark.asyncio
async def test_scope_blocks_mutation_via_executor(tmp_path):
    (tmp_path / "changed.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("b = 2\n", encoding="utf-8")

    from code_review_harness.governance.scope import ReviewScope

    scope = ReviewScope(root=Path(tmp_path), changed_files=frozenset({(tmp_path / "changed.py").resolve()}))
    checker = PermissionChecker(mode=PermissionMode.DEFAULT)
    checker.set_scope(scope)
    executor = make_executor(tmp_path, checker=checker, approval=auto_approve)

    # Reading anywhere is fine.
    read = await executor.execute(ToolUse(id="c1", name="read_file", input={"path": "other.py"}))
    assert not read.is_error

    # Writing outside the scope is denied even with auto-approval.
    from code_review_harness.tools.base import BaseTool, ToolOutcome
    from pydantic import BaseModel

    class _WriteInput(BaseModel):
        path: str
        content: str

    class _FakeWrite(BaseTool):
        name = "fake_write"
        description = "mutates a file"
        input_model = _WriteInput

        async def execute(self, arguments, context):
            return ToolOutcome(output="written")

    registry = default_tool_registry()
    registry.register(_FakeWrite())
    executor = GovernedToolExecutor(
        tool_registry=registry,
        checker=checker,
        cwd=Path(tmp_path),
        approval_gate=auto_approve,
    )
    blocked = await executor.execute(
        ToolUse(id="c2", name="fake_write", input={"path": "other.py", "content": "x"})
    )
    assert blocked.is_error
    assert "outside the review scope" in blocked.output
