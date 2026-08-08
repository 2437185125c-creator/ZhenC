"""Validation tools: compile-check and run tests.

The fix agent uses these to verify its own changes.  They are classified as
read-only for governance purposes (they do not modify tracked source), which
lets the fix loop iterate without an approval prompt on every check.
"""

from __future__ import annotations

import asyncio
import py_compile
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from code_review_harness.tools.base import BaseTool, ToolExecutionContext, ToolOutcome
from code_review_harness.utils.paths import safe_resolve


class RunChecksInput(BaseModel):
    files: list[str] = Field(default_factory=list, description="Python files to compile-check.")
    run_tests: bool = Field(default=True, description="Run pytest after compiling.")


class RunChecksTool(BaseTool):
    name = "run_checks"
    description = "Compile-check the given Python files and optionally run the test suite."
    read_only = True

    input_model = RunChecksInput

    async def execute(self, arguments: RunChecksInput, context: ToolExecutionContext) -> ToolOutcome:
        output: list[str] = []
        compile_failed = False

        for name in arguments.files:
            try:
                resolved = safe_resolve(context.cwd, name)
            except ValueError as exc:
                output.append(f"compile {name}: {exc}")
                compile_failed = True
                continue
            try:
                py_compile.compile(str(resolved), doraise=True)
                output.append(f"compile {name}: ok")
            except py_compile.PyCompileError as exc:
                output.append(f"compile {name}: FAILED\n{exc}")
                compile_failed = True

        if arguments.run_tests:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
                cwd=str(context.cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode("utf-8", errors="replace").strip()
            # exit code 5 == "no tests collected" -> treat as passing.
            tests_ok = proc.returncode in (0, 5)
            output.append(f"pytest: {'ok' if tests_ok else 'FAILED'} (exit {proc.returncode})")
            if text:
                output.append(text[-3000:])

        success = not compile_failed
        if arguments.run_tests:
            success = success and tests_ok
        body = "\n".join(output)
        return ToolOutcome(output=body, is_error=not success)
