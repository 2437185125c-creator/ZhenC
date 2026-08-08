"""Render a :class:`ReviewReport` as markdown or JSON for the CLI."""

from __future__ import annotations

import json

from code_review_harness.review.models import ReviewReport


def to_json(report: ReviewReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def to_markdown(report: ReviewReport) -> str:
    lines = [
        f"# Review Report — {report.repo_path}",
        "",
        f"**{report.count} finding(s)**",
        "",
    ]
    if report.notes:
        lines.append("**Notes**")
        lines.extend(f"- {note}" for note in report.notes)
        lines.append("")

    current_file: str | None = None
    for finding in report.sorted_findings():
        if finding.file_path != current_file:
            current_file = finding.file_path
            lines.append(f"## `{current_file}`")
            lines.append("")
        location = f":{finding.line}" if finding.line is not None else ""
        lines.append(
            f"- **[{finding.severity.value}]** `{finding.rule_id}` "
            f"`{finding.category.value}` {location} — {finding.message}"
        )
        if finding.suggestion:
            lines.append(f"  - suggestion: {finding.suggestion}")
    if not report.findings:
        lines.append("_No findings — the change looks clean._")
    return "\n".join(lines) + "\n"
