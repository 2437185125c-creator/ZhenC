"""Unit tests for read_file and grep tools."""
from __future__ import annotations

import pytest

from code_review_harness.tools.base import ToolExecutionContext
from code_review_harness.tools.file_tools import GrepTool, ReadFileTool
from code_review_harness.utils.paths import PathEscapeError


@pytest.mark.asyncio
async def test_read_file_returns_numbered_lines(tmp_path):
    src = tmp_path / "app.py"
    src.write_text("line one\nline two\nline three\n", encoding="utf-8")
    context = ToolExecutionContext(cwd=tmp_path)

    outcome = await ReadFileTool().execute(ReadFileTool.input_model(path="app.py"), context)

    assert not outcome.is_error
    assert "1\tline one" in outcome.output
    assert "3\tline three" in outcome.output


@pytest.mark.asyncio
async def test_read_file_offset_and_limit(tmp_path):
    src = tmp_path / "app.py"
    src.write_text("\n".join(f"line {i}" for i in range(10)), encoding="utf-8")
    context = ToolExecutionContext(cwd=tmp_path)

    outcome = await ReadFileTool().execute(
        ReadFileTool.input_model(path="app.py", offset=2, limit=3), context
    )

    assert "3\tline 2" in outcome.output
    assert "5\tline 4" in outcome.output
    assert "line 9" not in outcome.output


@pytest.mark.asyncio
async def test_read_file_missing(tmp_path):
    context = ToolExecutionContext(cwd=tmp_path)
    outcome = await ReadFileTool().execute(ReadFileTool.input_model(path="missing.py"), context)
    assert outcome.is_error


@pytest.mark.asyncio
async def test_grep_finds_matches(tmp_path):
    (tmp_path / "a.py").write_text("import os\n# TODO: clean\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def f():\n    pass\n", encoding="utf-8")
    context = ToolExecutionContext(cwd=tmp_path)

    outcome = await GrepTool().execute(GrepTool.input_model(pattern="TODO"), context)

    assert not outcome.is_error
    assert "a.py:2" in outcome.output
    assert "b.py" not in outcome.output


@pytest.mark.asyncio
async def test_grep_no_matches(tmp_path):
    context = ToolExecutionContext(cwd=tmp_path)
    outcome = await GrepTool().execute(GrepTool.input_model(pattern="ZZZ_NOT_THERE"), context)
    assert not outcome.is_error
    assert "No matches" in outcome.output


def test_safe_resolve_blocks_escape(tmp_path):
    with pytest.raises(PathEscapeError):
        from code_review_harness.utils.paths import safe_resolve

        safe_resolve(tmp_path, "../outside.txt")
