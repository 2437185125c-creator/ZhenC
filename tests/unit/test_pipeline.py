"""Integration tests for the review pipeline (mock LLM drives the loop)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_review_harness.harness.messages import ToolUse
from code_review_harness.llm.base import LLMResponse
from code_review_harness.llm.mock_provider import MockProvider
from code_review_harness.review.pipeline import ReviewPipeline
from code_review_harness.review.schema import ReviewOutputError

VALID_FINDINGS = [
    {
        "rule_id": "REVIEW-001",
        "category": "bug",
        "severity": "medium",
        "file_path": "app.py",
        "line": 5,
        "message": "Potential issue found by model",
        "suggestion": "Fix it",
    }
]


def review_json(findings=None):
    return json.dumps(
        {"findings": VALID_FINDINGS if findings is None else findings, "summary": "done"}
    )


def add_bug(repo: Path) -> None:
    (repo / "app.py").write_text(
        "def risky():\n    try:\n        return 1 / 0\n    except:\n        return None\n",
        encoding="utf-8",
    )


async def run_pipeline(tmp_git_repo, responses):
    provider = MockProvider(responses)
    pipeline = ReviewPipeline(provider=provider, cwd=tmp_git_repo)
    return await pipeline.review(), provider


@pytest.mark.asyncio
async def test_pipeline_produces_report_with_static_and_model_findings(tmp_git_repo):
    add_bug(tmp_git_repo)
    responses = [
        LLMResponse(text="inspecting", tool_uses=(ToolUse(id="c1", name="read_file", input={"path": "app.py"}),)),
        LLMResponse(text=review_json()),
    ]
    report, _ = await run_pipeline(tmp_git_repo, responses)

    assert report.count >= 1
    # Static analyzer must have caught the bare except.
    assert any(f.rule_id == "PY-BARE-EXCEPT" for f in report.findings)
    # Model finding merged in.
    assert any(f.rule_id == "REVIEW-001" for f in report.findings)


@pytest.mark.asyncio
async def test_pipeline_repairs_invalid_json_once(tmp_git_repo):
    add_bug(tmp_git_repo)
    responses = [
        LLMResponse(text="this is not json at all"),
        LLMResponse(text=review_json()),
    ]
    report, provider = await run_pipeline(tmp_git_repo, responses)

    assert any(f.rule_id == "REVIEW-001" for f in report.findings)
    # The repair is a second user message in the same conversation.
    assert len(provider.requests) == 2
    assert provider.requests[1].messages[-1].is_tool_response is False


@pytest.mark.asyncio
async def test_pipeline_raises_when_json_never_validates(tmp_git_repo):
    add_bug(tmp_git_repo)
    responses = [
        LLMResponse(text="not json"),
        LLMResponse(text="still not json"),
    ]
    with pytest.raises(ReviewOutputError):
        await run_pipeline(tmp_git_repo, responses)


@pytest.mark.asyncio
async def test_pipeline_empty_diff_is_ok(tmp_git_repo):
    # No changes at all: the agent should still produce a report.
    responses = [LLMResponse(text=review_json([]))]
    report, _ = await run_pipeline(tmp_git_repo, responses)
    assert report.count == 0
    assert any("static analysis" in n for n in report.notes)
