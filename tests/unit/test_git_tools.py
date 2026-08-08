"""Unit tests for the git tools against a real throwaway repo."""
from __future__ import annotations

import pytest

from code_review_harness.tools.base import ToolExecutionContext
from code_review_harness.tools.git_tools import GitDiffTool, GitStatusTool


@pytest.mark.asyncio
async def test_git_status_clean(tmp_git_repo):
    context = ToolExecutionContext(cwd=tmp_git_repo)
    outcome = await GitStatusTool().execute(GitStatusTool.input_model(), context)
    assert not outcome.is_error
    assert "Working tree clean" in outcome.output


@pytest.mark.asyncio
async def test_git_diff_shows_unstaged_change(tmp_git_repo):
    (tmp_git_repo / "app.py").write_text("def add(a, b):\n    return a + b + 1\n", encoding="utf-8")
    context = ToolExecutionContext(cwd=tmp_git_repo)

    outcome = await GitDiffTool().execute(GitDiffTool.input_model(), context)

    assert not outcome.is_error
    assert "app.py" in outcome.output
    assert "+    return a + b + 1" in outcome.output


@pytest.mark.asyncio
async def test_git_diff_empty_when_no_changes(tmp_git_repo):
    context = ToolExecutionContext(cwd=tmp_git_repo)
    outcome = await GitDiffTool().execute(GitDiffTool.input_model(), context)
    assert "No changes" in outcome.output


@pytest.mark.asyncio
async def test_git_diff_staged(tmp_git_repo):
    (tmp_git_repo / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    context = ToolExecutionContext(cwd=tmp_git_repo)
    outcome = await GitDiffTool().execute(GitDiffTool.input_model(staged=True), context)
    assert "No changes" in outcome.output
