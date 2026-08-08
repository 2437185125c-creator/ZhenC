"""Domain models for code review results.

These dataclasses are the contract between the review pipeline, the fix
pipeline, the workflow state machine and the report/eval layers.  Keeping
them in one module keeps the coupling surface small.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Impact ranking of a finding."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    def rank(self) -> int:
        return {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}[self.value]


class FindingCategory(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"


@dataclass(frozen=True)
class Finding:
    """A single issue the review identified."""

    rule_id: str
    category: FindingCategory
    severity: Severity
    file_path: str
    line: int | None
    message: str
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "rule_id": self.rule_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line": self.line,
            "message": self.message,
        }
        if self.suggestion is not None:
            data["suggestion"] = self.suggestion
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        return cls(
            rule_id=data["rule_id"],
            category=FindingCategory(data["category"]),
            severity=Severity(data["severity"]),
            file_path=data["file_path"],
            line=data.get("line"),
            message=data["message"],
            suggestion=data.get("suggestion"),
        )


@dataclass
class ReviewReport:
    """The full result of reviewing one repository."""

    repo_path: str
    findings: list[Finding] = field(default_factory=list)
    # Non-fatal observations from the review run itself (e.g. files skipped).
    notes: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.findings)

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (-f.severity.rank(), f.file_path, f.line or 0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "notes": self.notes,
            "findings": [f.to_dict() for f in self.sorted_findings()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewReport":
        return cls(
            repo_path=data["repo_path"],
            notes=list(data.get("notes", [])),
            findings=[Finding.from_dict(f) for f in data.get("findings", [])],
        )
