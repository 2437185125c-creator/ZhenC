"""Unit tests for the markdown/JSON report renderers."""
from __future__ import annotations

from code_review_harness.review.models import Finding, FindingCategory, ReviewReport, Severity
from code_review_harness.review.reporting import to_json, to_markdown


def make_report() -> ReviewReport:
    report = ReviewReport(repo_path="/tmp/repo", notes=["static analysis: 1 finding(s)"])
    report.findings = [
        Finding(
            rule_id="PY-BARE-EXCEPT",
            category=FindingCategory.BUG,
            severity=Severity.MEDIUM,
            file_path="app.py",
            line=3,
            message="Bare except clause.",
            suggestion="Use except Exception.",
        )
    ]
    return report


def test_markdown_contains_finding_fields():
    md = to_markdown(make_report())
    assert "# Review Report" in md
    assert "app.py" in md
    assert "PY-BARE-EXCEPT" in md
    assert "medium" in md
    assert "suggestion: Use except Exception." in md


def test_markdown_empty_report():
    md = to_markdown(ReviewReport(repo_path="/tmp/x"))
    assert "No findings" in md


def test_json_roundtrip():
    report = make_report()
    import json

    data = json.loads(to_json(report))
    assert data["repo_path"] == "/tmp/repo"
    assert data["findings"][0]["rule_id"] == "PY-BARE-EXCEPT"
