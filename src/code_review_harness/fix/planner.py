"""Prompt construction for the fix agent.

The fix agent receives the review findings and must produce a corrected file.
It has three tools: ``write_file`` (apply a full-file fix), ``read_file`` and
``run_checks`` (verify).  The harness then validates deterministically.
"""

from __future__ import annotations

from code_review_harness.review.models import ReviewReport


def build_fix_system_prompt() -> str:
    return (
        "You are a Python code fixer. You are given review findings for a change "
        "and must fix the issues.\n\n"
        "Rules:\n"
        "1. Read the relevant files first, then fix them with write_file "
        "(full file content).\n"
        "2. Fix only the issues you are confident about. Do not rewrite code "
        "unnecessarily.\n"
        "3. Only modify files listed in the review scope.\n"
        "4. After applying a fix, call run_checks to verify your changes. "
        "If checks fail, inspect the output and fix again.\n"
        "5. When you believe the fixes are complete and checks pass, stop and "
        "give a one-paragraph summary of what you changed."
    )


def build_fix_user_prompt(report: ReviewReport) -> str:
    lines = []
    for f in report.sorted_findings():
        loc = f"{f.file_path}:{f.line or '?'}"
        lines.append(
            f"- [{f.severity.value}] {loc} {f.rule_id}: {f.message}"
            + (f" | suggestion: {f.suggestion}" if f.suggestion else "")
        )
    findings_block = "\n".join(lines) or "  (no findings — nothing to fix)"
    return (
        f"Repository: {report.repo_path}\n\n"
        f"## Findings to fix\n{findings_block}\n\n"
        "Fix the issues above using the tools, then verify with run_checks."
    )
