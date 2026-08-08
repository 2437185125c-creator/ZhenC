"""Integration tests for the fix pipeline — the validation feedback loop."""
from __future__ import annotations

from pathlib import Path

import pytest

from code_review_harness.fix.pipeline import FixPipeline
from code_review_harness.governance.approval import auto_approve
from code_review_harness.harness.messages import ToolUse
from code_review_harness.llm.base import LLMResponse
from code_review_harness.llm.mock_provider import MockProvider
from code_review_harness.review.models import Finding, FindingCategory, ReviewReport, Severity

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"


@pytest.fixture
def buggy_repo(tmp_git_repo: Path) -> Path:
    """A repo whose 'change' introduces an off-by-sign bug and has a failing test."""
    (tmp_git_repo / "test_app.py").write_text(
        "from app import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    subprocess_commit(tmp_git_repo)
    # The change under review introduces the bug.
    (tmp_git_repo / "app.py").write_text(BUGGY, encoding="utf-8")
    return tmp_git_repo


def subprocess_commit(repo: Path) -> None:
    import subprocess

    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "add test"], cwd=repo, check=True)


def make_report(repo: Path) -> ReviewReport:
    return ReviewReport(
        repo_path=str(repo),
        findings=[
            Finding(
                rule_id="TEST-BUG",
                category=FindingCategory.BUG,
                severity=Severity.HIGH,
                file_path="app.py",
                line=1,
                message="add() subtracts instead of adding",
                suggestion="Return a + b",
            )
        ],
    )


def write_fix(use_id: str, path: str, content: str) -> LLMResponse:
    return LLMResponse(
        text="applying fix",
        tool_uses=(ToolUse(id=use_id, name="write_file", input={"path": path, "content": content}),),
    )


@pytest.mark.asyncio
async def test_fix_pipeline_applies_fix_and_passes_validation(buggy_repo):
    responses = [
        write_fix("c1", "app.py", FIXED),
        LLMResponse(
            text="checking",
            tool_uses=(ToolUse(id="c2", name="run_checks", input={"files": ["app.py"]}),),
        ),
        LLMResponse(text="fixed"),
    ]
    provider = MockProvider(responses)
    pipeline = FixPipeline(
        provider=provider,
        cwd=buggy_repo,
        mode="full_auto",
        approval_gate=auto_approve,
    )
    result = await pipeline.fix(make_report(buggy_repo))

    assert result.success
    assert (buggy_repo / "app.py").read_text(encoding="utf-8") == FIXED
    assert "app.py" in [str(p.name) for p in result.changed_files]


@pytest.mark.asyncio
async def test_fix_pipeline_retries_after_failed_validation(buggy_repo):
    # First run leaves the bug in place -> validation fails -> the feedback
    # message triggers a continuation in which the agent fixes it.
    responses = [
        write_fix("c1", "app.py", BUGGY),  # no-op -> attempt 1 validation fails
        LLMResponse(text="done for now"),
        write_fix("c2", "app.py", FIXED),  # continuation fixes it
        LLMResponse(text="done"),
    ]
    provider = MockProvider(responses)
    pipeline = FixPipeline(
        provider=provider,
        cwd=buggy_repo,
        mode="full_auto",
        approval_gate=auto_approve,
        max_fix_attempts=3,
    )
    result = await pipeline.fix(make_report(buggy_repo))

    assert result.success
    assert result.attempts == 2
    assert (buggy_repo / "app.py").read_text(encoding="utf-8") == FIXED


@pytest.mark.asyncio
async def test_fix_pipeline_rolls_back_when_all_attempts_fail(buggy_repo):
    responses = [
        write_fix("c1", "app.py", BUGGY),  # agent never fixes it
        LLMResponse(text="I give up"),
    ]
    provider = MockProvider(responses)
    pipeline = FixPipeline(
        provider=provider,
        cwd=buggy_repo,
        mode="full_auto",
        approval_gate=auto_approve,
        max_fix_attempts=1,  # no retries -> roll back immediately
    )
    result = await pipeline.fix(make_report(buggy_repo))

    assert not result.success
    assert result.rolled_back
    # Rolled back to the buggy snapshot (the pre-fix working-tree state).
    assert (buggy_repo / "app.py").read_text(encoding="utf-8") == BUGGY
