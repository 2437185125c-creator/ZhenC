"""Integration tests for the top-level workflow orchestrator."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_review_harness.governance.approval import auto_approve, auto_deny
from code_review_harness.harness.messages import ToolUse
from code_review_harness.llm.base import LLMResponse
from code_review_harness.llm.mock_provider import MockProvider
from code_review_harness.workflow.state_machine import Stage
from code_review_harness.workflow.workflow import ReviewWorkflow

FIXED = "def add(a, b):\n    return a + b\n"

REVIEW_JSON = json.dumps(
    {
        "findings": [
            {
                "rule_id": "REVIEW-1",
                "category": "bug",
                "severity": "high",
                "file_path": "app.py",
                "line": 1,
                "message": "add() subtracts instead of adding",
                "suggestion": "Return a + b",
            }
        ],
        "summary": "one bug",
    }
)


@pytest.fixture
def buggy_repo(tmp_git_repo: Path) -> Path:
    import subprocess

    (tmp_git_repo / "test_app.py").write_text(
        "from app import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tmp_git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "add test"], cwd=tmp_git_repo, check=True)
    (tmp_git_repo / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    return tmp_git_repo


def write_fix(use_id: str, content: str) -> LLMResponse:
    return LLMResponse(
        text="applying fix",
        tool_uses=(ToolUse(id=use_id, name="write_file", input={"path": "app.py", "content": content}),),
    )


@pytest.mark.asyncio
async def test_workflow_full_cycle_with_fix(buggy_repo):
    responses = [
        LLMResponse(text=REVIEW_JSON),
        write_fix("c1", FIXED),
        LLMResponse(
            text="checking",
            tool_uses=(ToolUse(id="c2", name="run_checks", input={"files": ["app.py"]}),),
        ),
        LLMResponse(text="done"),
    ]
    provider = MockProvider(responses)
    approvals: list[str] = []

    async def tracking_approval(tool: str, reason: str) -> bool:
        approvals.append(tool)
        return True

    workflow = ReviewWorkflow(
        provider=provider,
        cwd=buggy_repo,
        mode="full_auto",
        plan_approval=tracking_approval,
        tool_approval=auto_approve,
    )
    result = await workflow.run()

    assert result.succeeded
    assert result.final_stage == Stage.DONE
    assert result.plan_approved
    assert approvals == ["apply_fixes"]
    assert result.report is not None and result.report.count >= 1
    assert result.fix is not None and result.fix.success
    assert (buggy_repo / "app.py").read_text(encoding="utf-8") == FIXED
    stages = [t.to_stage for t in result.transitions]
    assert Stage.REVIEW in stages and Stage.APPLY in stages and Stage.VALIDATE in stages


@pytest.mark.asyncio
async def test_workflow_plan_rejected_stops_before_fix(buggy_repo):
    responses = [LLMResponse(text=REVIEW_JSON)]
    provider = MockProvider(responses)
    workflow = ReviewWorkflow(
        provider=provider,
        cwd=buggy_repo,
        mode="full_auto",
        plan_approval=auto_deny,
    )
    result = await workflow.run()

    assert result.succeeded  # report-only end is a normal DONE
    assert not result.plan_approved
    assert result.fix is None
    stages = [t.to_stage for t in result.transitions]
    assert Stage.APPLY not in stages
    assert Stage.REPORT in stages
    # The repository must be untouched.
    assert "return a - b" in (buggy_repo / "app.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_workflow_no_findings_skips_fix(buggy_repo):
    responses = [
        LLMResponse(text=json.dumps({"findings": [], "summary": "clean"})),
    ]
    provider = MockProvider(responses)
    workflow = ReviewWorkflow(provider=provider, cwd=buggy_repo, mode="full_auto")
    result = await workflow.run()

    assert result.succeeded
    assert result.fix is None
    assert result.report is not None and result.report.count == 0


@pytest.mark.asyncio
async def test_workflow_step_budget_aborts(buggy_repo):
    # Review stage uses one tool execution, but the budget allows zero.
    responses = [
        LLMResponse(
            text="reading",
            tool_uses=(ToolUse(id="c0", name="read_file", input={"path": "app.py"}),),
        ),
        LLMResponse(text=REVIEW_JSON),
    ]
    provider = MockProvider(responses)
    workflow = ReviewWorkflow(
        provider=provider,
        cwd=buggy_repo,
        mode="full_auto",
        max_tool_steps=0,
    )
    result = await workflow.run()

    assert result.final_stage == Stage.FAILED
    assert not result.succeeded
