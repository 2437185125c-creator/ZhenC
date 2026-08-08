"""Deterministic validation for the fix feedback loop.

After the agent applies fixes, the harness *always* verifies: compile-check the
changed files and run the test suite.  Failure output is fed back to the agent
for another attempt (up to a budget), which is the harness's feedback-loop
mechanism for the fix stage.
"""

from __future__ import annotations

import asyncio
import py_compile
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ValidationResult:
    success: bool
    output: str


async def validate_fix(cwd: Path, changed_files: list[Path], run_tests: bool = True) -> ValidationResult:
    """Compile-check ``changed_files`` and run pytest inside ``cwd``."""
    lines: list[str] = []
    success = True

    for path in changed_files:
        if not path.suffix == ".py":
            continue
        try:
            py_compile.compile(str(path.resolve()), doraise=True)
            lines.append(f"compile {path}: ok")
        except py_compile.PyCompileError as exc:
            lines.append(f"compile {path}: FAILED\n{exc}")
            success = False

    if run_tests:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        text = stdout.decode("utf-8", errors="replace").strip()
        tests_ok = proc.returncode in (0, 5)  # 5 = no tests collected
        lines.append(f"pytest: {'ok' if tests_ok else 'FAILED'} (exit {proc.returncode})")
        if text:
            lines.append(text[-3000:])
        success = success and tests_ok

    return ValidationResult(success=success, output="\n".join(lines))
