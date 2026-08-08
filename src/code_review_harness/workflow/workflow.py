"""Workflow orchestrator — wires review and fix into the state machine.

The workflow is the top-level harness: it runs the review pipeline, proposes a
fix plan for human approval, runs the fix pipeline (which itself applies and
validates), and reports.  Every stage change is recorded, invalid transitions
are rejected by the FSM, and the whole run is capped by a step budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from code_review_harness.fix.pipeline import FixPipeline, FixResult
from code_review_harness.governance.approval import ApprovalGate, auto_approve
from code_review_harness.governance.modes import PermissionMode
from code_review_harness.governance.permissions import PermissionChecker
from code_review_harness.harness.loop import EventSink
from code_review_harness.llm.base import LLMProvider
from code_review_harness.review.models import ReviewReport
from code_review_harness.review.pipeline import ReviewPipeline
from code_review_harness.workflow.state_machine import (
    BudgetExceeded,
    Stage,
    WorkflowBudget,
    WorkflowState,
)

log = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    report: ReviewReport | None = None
    fix: FixResult | None = None
    final_stage: Stage = Stage.START
    plan_approved: bool = False
    transitions: list = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.final_stage == Stage.DONE


class ReviewWorkflow:
    """Top-level orchestration: PLAN → REVIEW → PROPOSE → APPROVE → APPLY → VALIDATE → REPORT."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        cwd: Path,
        mode: PermissionMode = PermissionMode.DEFAULT,
        plan_approval: ApprovalGate | None = None,
        tool_approval: ApprovalGate | None = None,
        fix: bool = True,
        max_fix_attempts: int = 3,
        max_turns: int | None = 12,
        max_tool_steps: int = 100,
        on_event: EventSink | None = None,
    ) -> None:
        self._provider = provider
        self._cwd = Path(cwd).resolve()
        self._checker = PermissionChecker(mode=mode)
        self._mode = mode
        self._plan_approval = plan_approval or auto_approve
        self._tool_approval = tool_approval
        self._do_fix = fix
        self._max_fix_attempts = max_fix_attempts
        self._max_turns = max_turns
        self._max_tool_steps = max_tool_steps
        self._on_event = on_event
        self._state = WorkflowState()
        self._budget = WorkflowBudget(max_tool_steps)

    async def run(self, repo_path: Path | None = None) -> WorkflowResult:
        repo = Path(repo_path or self._cwd).resolve()
        budget_sink = self._budget.event_sink
        state = self._state
        try:
            state.transition(Stage.PLAN, note="compute change and scope")

            state.transition(Stage.REVIEW)
            report = await ReviewPipeline(
                provider=self._provider,
                cwd=repo,
                mode=self._mode,
                checker=self._checker,
                max_turns=self._max_turns,
                on_event=budget_sink,
            ).review()

            state.transition(Stage.PROPOSE, note=f"{report.count} finding(s)")
            if report.count == 0 or not self._do_fix:
                state.transition(Stage.REPORT, note="nothing to fix")
                state.transition(Stage.DONE)
                return WorkflowResult(
                    report=report,
                    final_stage=Stage.DONE,
                    transitions=list(state.transitions),
                )

            state.transition(Stage.APPROVE)
            plan = self._build_plan_summary(report)
            approved = await self._plan_approval("apply_fixes", plan)
            if not approved:
                state.transition(Stage.REPORT, note="plan rejected by user")
                state.transition(Stage.DONE)
                return WorkflowResult(
                    report=report,
                    final_stage=Stage.DONE,
                    plan_approved=False,
                    transitions=list(state.transitions),
                )

            state.transition(Stage.APPLY, note="run fix pipeline")
            fix_result = await FixPipeline(
                provider=self._provider,
                cwd=repo,
                checker=self._checker,
                mode=self._mode,
                approval_gate=self._tool_approval,
                max_fix_attempts=self._max_fix_attempts,
                max_turns=self._max_turns,
                on_event=budget_sink,
            ).fix(report)

            state.transition(Stage.VALIDATE, note="compile + tests")
            if fix_result.success:
                state.transition(Stage.REPORT, note=f"fix applied in {fix_result.attempts} attempt(s)")
                state.transition(Stage.DONE)
                return WorkflowResult(
                    report=report,
                    fix=fix_result,
                    final_stage=Stage.DONE,
                    plan_approved=True,
                    transitions=list(state.transitions),
                )

            state.transition(Stage.FAILED, note="fix validation failed; rolled back")
            return WorkflowResult(
                report=report,
                fix=fix_result,
                final_stage=Stage.FAILED,
                plan_approved=True,
                transitions=list(state.transitions),
            )
        except BudgetExceeded as exc:
            log.warning("workflow aborted: %s", exc)
            if state.current != Stage.FAILED:
                state.transition(Stage.FAILED, note=str(exc))
            return WorkflowResult(final_stage=Stage.FAILED, transitions=list(state.transitions))

    def _build_plan_summary(self, report: ReviewReport) -> str:
        by_file: dict[str, int] = {}
        for f in report.findings:
            by_file[f.file_path] = by_file.get(f.file_path, 0) + 1
        files = ", ".join(f"{path} ({count})" for path, count in sorted(by_file.items()))
        return (
            f"Proposed fix plan: {report.count} finding(s) across {len(by_file)} file(s): {files}. "
            "Approve to apply fixes and run validation."
        )
