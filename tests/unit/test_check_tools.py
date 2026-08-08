"""Unit tests for the validation/check tool and write_file tool."""
from __future__ import annotations

import pytest

from code_review_harness.tools.base import ToolExecutionContext
from code_review_harness.tools.check_tools import RunChecksTool
from code_review_harness.tools.file_tools import WriteFileTool
from code_review_harness.tools import fix_tool_registry


@pytest.mark.asyncio
async def test_write_file_creates_and_overwrites(tmp_path):
    context = ToolExecutionContext(cwd=tmp_path)
    tool = WriteFileTool()
    result = await tool.execute(WriteFileTool.input_model(path="new.txt", content="hello"), context)
    assert not result.is_error
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "hello"

    await tool.execute(WriteFileTool.input_model(path="new.txt", content="world"), context)
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "world"


@pytest.mark.asyncio
async def test_write_file_blocks_escape(tmp_path):
    context = ToolExecutionContext(cwd=tmp_path)
    result = await WriteFileTool().execute(
        WriteFileTool.input_model(path="../evil.txt", content="x"), context
    )
    assert result.is_error


@pytest.mark.asyncio
async def test_run_checks_reports_compile_failure(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    context = ToolExecutionContext(cwd=tmp_path)
    result = await RunChecksTool().execute(
        RunChecksTool.input_model(files=["bad.py"], run_tests=False), context
    )
    assert result.is_error
    assert "FAILED" in result.output


@pytest.mark.asyncio
async def test_run_checks_compile_ok_without_tests(tmp_path):
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    context = ToolExecutionContext(cwd=tmp_path)
    result = await RunChecksTool().execute(
        RunChecksTool.input_model(files=["ok.py"], run_tests=False), context
    )
    assert not result.is_error
    assert "compile ok.py: ok" in result.output


@pytest.mark.asyncio
async def test_fix_registry_contains_write_and_checks():
    registry = fix_tool_registry()
    names = {t.name for t in registry.list_tools()}
    assert {"write_file", "run_checks", "read_file", "git_diff"} <= names
