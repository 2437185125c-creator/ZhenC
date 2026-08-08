"""Governed tool executor — wraps tool execution with permission + approval.

This is where the harness's two constraint pillars meet: every tool call first
passes the :class:`PermissionChecker`, and mutating calls in default mode pause
for the :class:`ApprovalGate` before running.
"""

from __future__ import annotations

from pathlib import Path

from code_review_harness.governance.approval import ApprovalGate, auto_deny
from code_review_harness.governance.permissions import PermissionChecker
from code_review_harness.harness.messages import ToolResult, ToolUse
from code_review_harness.tools.base import ToolRegistry
from code_review_harness.tools.executor import SimpleToolExecutor


def _extract_file_path(raw_input: dict) -> str | None:
    for key in ("file_path", "path", "root"):
        value = raw_input.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _extract_command(raw_input: dict) -> str | None:
    value = raw_input.get("command")
    if isinstance(value, str) and value.strip():
        return value
    return None


class GovernedToolExecutor:
    """Runs tools after permission checks and, when needed, human approval."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        checker: PermissionChecker,
        cwd: Path,
        approval_gate: ApprovalGate | None = None,
        event_sink=None,
    ) -> None:
        self._inner = SimpleToolExecutor(tool_registry, cwd)
        self._registry = tool_registry
        self._checker = checker
        self._cwd = cwd
        self._approval_gate = approval_gate or auto_deny
        self._event_sink = event_sink

    async def _emit(self, name: str, payload: dict) -> None:
        if self._event_sink is not None:
            await self._event_sink(name, payload)

    async def execute(self, tool_use: ToolUse) -> ToolResult:
        tool = self._registry.get(tool_use.name)
        if tool is None:
            # Unknown tools fall through to the raw executor, which reports the error.
            return await self._inner.execute(tool_use)

        file_path = _extract_file_path(tool_use.input)
        if file_path:
            # Normalize to an absolute path so scope/path rules match consistently.
            candidate = Path(file_path).expanduser()
            if not candidate.is_absolute():
                candidate = self._cwd / candidate
            file_path = str(candidate.resolve())
        command = _extract_command(tool_use.input)
        is_read_only = True
        try:
            parsed = tool.input_model.model_validate(tool_use.input)
            is_read_only = tool.is_read_only(parsed)
        except Exception:
            # Invalid input: let the raw executor produce the canonical error.
            return await self._inner.execute(tool_use)

        decision = self._checker.evaluate(
            tool_use.name,
            is_read_only=is_read_only,
            file_path=file_path,
            command=command,
        )
        if not decision.allowed:
            if decision.requires_confirmation:
                await self._emit(
                    "approval_required",
                    {"tool": tool_use.name, "reason": decision.reason},
                )
                approved = await self._approval_gate(tool_use.name, decision.reason)
                if approved:
                    return await self._inner.execute(tool_use)
                return ToolResult(
                    id=tool_use.id,
                    name=tool_use.name,
                    output=f"Permission denied: {decision.reason}",
                    is_error=True,
                )
            await self._emit("permission_denied", {"tool": tool_use.name, "reason": decision.reason})
            return ToolResult(
                id=tool_use.id,
                name=tool_use.name,
                output=f"Permission denied: {decision.reason}",
                is_error=True,
            )

        return await self._inner.execute(tool_use)
