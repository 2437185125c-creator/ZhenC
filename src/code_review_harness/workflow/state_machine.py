"""Explicit workflow state machine.

The state machine makes the workflow *controllable and observable*: the agent
cannot silently skip stages, every transition is logged, invalid transitions
are rejected, and the whole run has a step budget.  This is the harness's
workflow-control pillar.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Stage(str, Enum):
    START = "start"
    PLAN = "plan"
    REVIEW = "review"
    PROPOSE = "propose"
    APPROVE = "approve"
    APPLY = "apply"
    VALIDATE = "validate"
    REPORT = "report"
    FAILED = "failed"
    DONE = "done"


# Allowed transitions: a strict FSM rejects anything not listed here.
# ``FAILED`` is an escape hatch reachable from every stage (budget aborts, etc.).
ALLOWED_EDGES: dict[Stage, set[Stage]] = {
    Stage.START: {Stage.PLAN, Stage.FAILED},
    Stage.PLAN: {Stage.REVIEW, Stage.FAILED},
    Stage.REVIEW: {Stage.PROPOSE, Stage.FAILED},
    Stage.PROPOSE: {Stage.APPROVE, Stage.REPORT, Stage.FAILED},
    Stage.APPROVE: {Stage.APPLY, Stage.REPORT, Stage.FAILED},
    Stage.APPLY: {Stage.VALIDATE, Stage.FAILED},
    Stage.VALIDATE: {Stage.REPORT, Stage.FAILED, Stage.APPLY},
    Stage.REPORT: {Stage.DONE, Stage.FAILED},
    Stage.FAILED: set(),
    Stage.DONE: set(),
}


@dataclass
class Transition:
    """One recorded state transition."""

    from_stage: Stage
    to_stage: Stage
    note: str = ""


class InvalidTransition(RuntimeError):
    """Raised when a transition is not allowed by the FSM."""


class BudgetExceeded(RuntimeError):
    """Raised when the workflow exceeds its overall step budget."""


class WorkflowState:
    """Tracks the current stage, validates transitions, and logs them."""

    def __init__(self) -> None:
        self.current: Stage = Stage.START
        self.transitions: list[Transition] = []

    @property
    def finished(self) -> bool:
        return self.current in {Stage.DONE, Stage.FAILED}

    def transition(self, to_stage: Stage, note: str = "") -> Transition:
        """Move to ``to_stage`` if allowed; raise :class:`InvalidTransition` otherwise."""
        allowed = ALLOWED_EDGES.get(self.current, set())
        if to_stage not in allowed:
            raise InvalidTransition(f"{self.current.value} -> {to_stage.value} is not allowed")
        record = Transition(from_stage=self.current, to_stage=to_stage, note=note)
        self.transitions.append(record)
        self.current = to_stage
        return record

    def path_summary(self) -> str:
        return " -> ".join(f"{t.from_stage.value}→{t.to_stage.value}" for t in self.transitions)


class WorkflowBudget:
    """Cross-stage cap on tool executions.

    Every ``tool_execution_completed`` event (from either pipeline) increments
    the counter; exceeding ``max_tool_steps`` aborts the workflow.
    """

    def __init__(self, max_tool_steps: int) -> None:
        self.max_tool_steps = max_tool_steps
        self.count = 0

    async def event_sink(self, name: str, payload: dict) -> None:
        del payload
        if name == "tool_execution_completed":
            self.count += 1
            if self.count > self.max_tool_steps:
                raise BudgetExceeded(
                    f"workflow exceeded its step budget of {self.max_tool_steps} tool executions"
                )
