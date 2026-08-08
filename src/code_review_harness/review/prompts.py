"""Prompt construction for the review agent.

The system prompt fixes the agent's job and its hard output contract (strict
JSON).  The user prompt carries the diff, the static-analysis hints and the
list of tools — everything the model needs to produce structured findings.
"""

from __future__ import annotations

from code_review_harness.review.models import Finding
from code_review_harness.review.schema import FindingPayload, ReviewPayload


def build_review_system_prompt() -> str:
    return (
        "You are a senior Python code reviewer. Your job is to review a git change "
        "and report findings.\n\n"
        "Rules:\n"
        "1. Use the provided tools (read_file, grep, git_diff, git_status) to inspect "
        "the repository before concluding.\n"
        "2. Report genuine issues only: real bugs, security risks, performance problems "
        "and maintainability concerns. Do not invent issues.\n"
        "3. Your FINAL message must be a single JSON object matching this schema exactly "
        "and nothing else (no prose, no markdown):\n"
        + _schema_example()
        + "\n"
        "4. Each finding must reference a file_path and a line number from the change.\n"
        "5. The static analysis hints in the prompt are advisory; verify them and keep "
        "only the ones you confirm."
    )


def _schema_example() -> str:
    example = ReviewPayload(
        findings=[
            FindingPayload(
                rule_id="REVIEW-001",
                category="bug",
                severity="high",
                file_path="app.py",
                line=12,
                message="Description of the issue.",
                suggestion="Suggested fix.",
            )
        ],
        summary="Short summary of the change quality.",
    )
    return example.model_dump_json(indent=2)


def _format_static_findings(findings: list[Finding]) -> str:
    if not findings:
        return "  (none)"
    lines = []
    for f in sorted(findings, key=lambda f: (-f.severity.rank(), f.file_path, f.line or 0)):
        loc = f"{f.file_path}:{f.line or '?'}"
        lines.append(f"  - [{f.severity.value}] {loc} {f.rule_id}: {f.message}")
    return "\n".join(lines)


def build_review_user_prompt(
    *,
    repo_path: str,
    diff_text: str,
    static_findings: list[Finding],
    changed_file_names: list[str],
) -> str:
    changed = "\n".join(f"  - {name}" for name in changed_file_names) or "  (none)"
    return (
        f"Repository under review: {repo_path}\n\n"
        f"## Changed files\n{changed}\n\n"
        f"## Git diff\n```diff\n{diff_text or '(empty diff)'}\n```\n\n"
        f"## Static analysis hints\n"
        f"These were produced by an AST analyzer; verify each before reporting.\n"
        f"{_format_static_findings(static_findings)}\n\n"
        "Now review the change. Use tools as needed, then output the JSON report."
    )
