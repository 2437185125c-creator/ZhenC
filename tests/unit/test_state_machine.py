"""Unit tests for the workflow state machine."""
from __future__ import annotations

import pytest

from code_review_harness.workflow.state_machine import (
    BudgetExceeded,
    InvalidTransition,
    Stage,
    WorkflowBudget,
    WorkflowState,
)


def test_happy_path_transitions():
    state = WorkflowState()
    state.transition(Stage.PLAN)
    state.transition(Stage.REVIEW)
    state.transition(Stage.PROPOSE)
    state.transition(Stage.APPROVE)
    state.transition(Stage.APPLY)
    state.transition(Stage.VALIDATE)
    state.transition(Stage.REPORT)
    state.transition(Stage.DONE)
    assert state.finished
    assert len(state.transitions) == 8


def test_invalid_transition_rejected():
    state = WorkflowState()
    state.transition(Stage.PLAN)
    with pytest.raises(InvalidTransition):
        state.transition(Stage.APPLY)  # PLAN -> APPLY is not allowed


def test_validate_can_retry_apply():
    state = WorkflowState()
    state.transition(Stage.PLAN)
    state.transition(Stage.REVIEW)
    state.transition(Stage.PROPOSE)
    state.transition(Stage.APPROVE)
    state.transition(Stage.APPLY)
    state.transition(Stage.VALIDATE)
    state.transition(Stage.APPLY)  # validation failed -> retry the apply stage
    assert state.current == Stage.APPLY


def test_path_summary():
    state = WorkflowState()
    state.transition(Stage.PLAN)
    state.transition(Stage.REVIEW)
    assert "start→plan" in state.path_summary()
    assert "plan→review" in state.path_summary()


@pytest.mark.asyncio
async def test_budget_counts_tool_executions():
    budget = WorkflowBudget(max_tool_steps=2)
    await budget.event_sink("assistant_message", {})
    await budget.event_sink("tool_execution_completed", {})
    assert budget.count == 1


@pytest.mark.asyncio
async def test_budget_raises_when_exceeded():
    budget = WorkflowBudget(max_tool_steps=0)
    with pytest.raises(BudgetExceeded):
        await budget.event_sink("tool_execution_completed", {})
