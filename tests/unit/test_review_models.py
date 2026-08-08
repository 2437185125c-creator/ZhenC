"""Unit tests for the review domain models."""
from __future__ import annotations

from code_review_harness.review.models import Finding, FindingCategory, ReviewReport, Severity


def make_finding(
    severity: Severity,
    file_path: str = "app.py",
    line: int | None = 1,
    suggestion: str | None = None,
) -> Finding:
    return Finding(
        rule_id="TEST-001",
        category=FindingCategory.BUG,
        severity=severity,
        file_path=file_path,
        line=line,
        message="a problem",
        suggestion=suggestion,
    )


def test_severity_ranking_order():
    assert Severity.CRITICAL.rank() > Severity.HIGH.rank() > Severity.MEDIUM.rank()
    assert Severity.MEDIUM.rank() > Severity.LOW.rank() > Severity.INFO.rank()


def test_finding_to_dict_and_back():
    finding = make_finding(Severity.HIGH, suggestion="fix it")
    data = finding.to_dict()
    assert data["severity"] == "high"
    assert data["category"] == "bug"
    assert data["suggestion"] == "fix it"

    restored = Finding.from_dict(data)
    assert restored == finding


def test_report_sorts_by_severity_then_path():
    report = ReviewReport(repo_path="/tmp/repo")
    report.findings = [
        make_finding(Severity.LOW, file_path="z.py", line=2),
        make_finding(Severity.HIGH, file_path="a.py", line=1),
        make_finding(Severity.CRITICAL, file_path="b.py", line=3),
    ]
    sorted_findings = report.sorted_findings()
    assert [f.severity for f in sorted_findings] == [
        Severity.CRITICAL,
        Severity.HIGH,
        Severity.LOW,
    ]


def test_report_to_dict_roundtrip():
    report = ReviewReport(repo_path="/tmp/repo", notes=["skipped a file"])
    report.findings = [make_finding(Severity.MEDIUM)]
    restored = ReviewReport.from_dict(report.to_dict())
    assert restored.repo_path == report.repo_path
    assert restored.notes == ["skipped a file"]
    assert restored.findings == report.findings
