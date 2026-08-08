"""Fix pipeline — applies review findings and verifies the result.

Flow:
1. snapshot the change (backup) so a failed run can roll back
2. run the fix agent: it reads files, applies fixes via ``write_file``, and
   self-verifies with ``run_checks``
3. deterministically validate (compile + tests); on failure, feed the output
   back to the agent and retry up to ``max_fix_attempts``
4. on final failure, roll back to the snapshot
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from code_review_harness.fix.applier import ChangeSet
from code_review_harness.fix.planner import build_fix_system_prompt, build_fix_user_prompt
from code_review_harness.fix.validator import validate_fix
from code_review_harness.governance.approval import ApprovalGate
from code_review_harness.governance.executor import GovernedToolExecutor
from code_review_harness.governance.modes import PermissionMode
from code_review_harness.governance.permissions import PermissionChecker
from code_review_harness.governance.scope import ReviewScope
from code_review_harness.harness.loop import AgentLoop, EventSink
from code_review_harness.llm.base import LLMProvider
from code_review_harness.review.diff import build_scope, changed_files_from_repo
from code_review_harness.review.models import ReviewReport
from code_review_harness.tools import fix_tool_registry

log = logging.getLogger(__name__)


@dataclass
class FixResult:
    success: bool
    validation_output: str = ""
    changed_files: list[Path] = field(default_factory=list)
    attempts: int = 0
    rolled_back: bool = False


class FixPipeline:
    """Drives the fix agent and owns the validation feedback loop."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        cwd: Path,
        checker: PermissionChecker | None = None,
        mode: PermissionMode = PermissionMode.DEFAULT,
        approval_gate: ApprovalGate | None = None,
        max_fix_attempts: int = 3,
        max_turns: int | None = 12,
        on_event: EventSink | None = None,
    ) -> None:
        from code_review_harness.governance.approval import auto_approve

        self._provider = provider
        self._cwd = Path(cwd).resolve()
        self._checker = checker or PermissionChecker(mode=mode)
        self._approval_gate = approval_gate or auto_approve
        self._max_fix_attempts = max_fix_attempts
        self._max_turns = max_turns
        self._on_event = on_event

    async def fix(self, report: ReviewReport) -> FixResult:
        changed_files = await changed_files_from_repo(self._cwd)
        scope = build_scope(self._cwd, changed_files)
        self._checker.set_scope(scope)

        changeset = self._snapshot(scope)
        registry = fix_tool_registry()
        loop = AgentLoop(
            provider=self._provider,
            tool_registry=registry,
            executor=GovernedToolExecutor(
                tool_registry=registry,
                checker=self._checker,
                cwd=self._cwd,
                approval_gate=self._approval_gate,
                event_sink=self._on_event,
            ),
            system_prompt=build_fix_system_prompt(),
            cwd=self._cwd,
            max_turns=self._max_turns,
            on_event=self._on_event,
        )

        result = await loop.run(build_fix_user_prompt(report))
        changeset.detect_writes()
        validation = await validate_fix(self._cwd, changeset.changed_python_files())
        attempts = 1

        while not validation.success and attempts < self._max_fix_attempts:
            attempts += 1
            result = await loop.continue_run(
                "The checks you ran did not pass. Validation output:\n"
                f"{validation.output}\n\n"
                "Inspect the failure, fix the cause, re-run run_checks, and "
                "confirm when checks pass."
            )
            changeset.detect_writes()
            validation = await validate_fix(self._cwd, changeset.changed_python_files())

        changed = changeset.detect_writes()
        if not validation.success:
            log.warning("fix validation failed after %d attempts; rolling back", attempts)
            changeset.rollback()
            return FixResult(
                success=False,
                validation_output=validation.output,
                changed_files=changed,
                attempts=attempts,
                rolled_back=True,
            )

        return FixResult(
            success=True,
            validation_output=validation.output,
            changed_files=changed,
            attempts=attempts,
            rolled_back=False,
        )

    def _snapshot(self, scope: ReviewScope) -> ChangeSet:
        changeset = ChangeSet(root=self._cwd)
        for path in scope.changed_files:
            if path.exists():
                changeset.backup(path)
        return changeset
