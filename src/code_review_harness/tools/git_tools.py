"""Read-only git tools.

The review agent needs to know what changed.  These tools surface working-tree
changes as unified diffs and status summaries.  They only read git state.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from code_review_harness.tools.base import BaseTool, ToolExecutionContext, ToolOutcome


async def _run_git(cwd: Path, *args: str, timeout: float = 30.0) -> tuple[str, int]:
    """Run a read-only git command and return (output, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return "git command timed out", 1
    if proc.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip() or stdout.decode("utf-8", errors="replace").strip()
        return message, proc.returncode
    return stdout.decode("utf-8", errors="replace").strip(), 0


class GitDiffInput(BaseModel):
    staged: bool = Field(default=False, description="Diff staged changes (git diff --cached) instead of working tree.")
    stat: bool = Field(default=False, description="Show a compact --stat summary instead of the full diff.")


class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Show the unified diff of uncommitted working-tree (or staged) changes."
    read_only = True

    input_model = GitDiffInput

    async def execute(self, arguments: GitDiffInput, context: ToolExecutionContext) -> ToolOutcome:
        args = ["git", "diff"]
        if arguments.staged:
            args.append("--cached")
        if arguments.stat:
            args.append("--stat")
        output, code = await _run_git(context.cwd, *args[1:])
        if code != 0:
            return ToolOutcome(output=output, is_error=True)
        if not output:
            return ToolOutcome(output="No changes to show.")
        return ToolOutcome(output=output)


class GitStatusInput(BaseModel):
    short: bool = Field(default=True, description="Use --short one-line-per-file output.")


class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Show the repository working-tree status."
    read_only = True

    input_model = GitStatusInput

    async def execute(self, arguments: GitStatusInput, context: ToolExecutionContext) -> ToolOutcome:
        args = ["git", "status"]
        if arguments.short:
            args.append("--short")
        output, code = await _run_git(context.cwd, *args[1:])
        if code != 0:
            return ToolOutcome(output=output, is_error=True)
        if not output:
            return ToolOutcome(output="Working tree clean.")
        return ToolOutcome(output=output)
