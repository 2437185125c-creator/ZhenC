"""Validation schema for structured LLM review output.

The agent must emit findings as JSON that validates against
:class:`ReviewPayload`; anything else is fed back to the model as an error and
retried.  This is the harness's *output-constraint* mechanism for the review
stage.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from code_review_harness.review.models import Finding, FindingCategory, ReviewReport, Severity

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class FindingPayload(BaseModel):
    """A single finding as emitted by the model."""

    rule_id: str
    category: FindingCategory
    severity: Severity
    file_path: str
    line: int | None = None
    message: str
    suggestion: str | None = None

    def to_finding(self) -> Finding:
        return Finding(
            rule_id=self.rule_id,
            category=self.category,
            severity=self.severity,
            file_path=self.file_path,
            line=self.line,
            message=self.message,
            suggestion=self.suggestion,
        )


class ReviewPayload(BaseModel):
    """The model's full review output."""

    findings: list[FindingPayload] = Field(default_factory=list)
    summary: str | None = None


class ReviewOutputError(ValueError):
    """Raised when the model's output cannot be parsed as a ReviewPayload."""


def parse_review_payload(text: str) -> ReviewPayload:
    """Parse and validate raw model output; raise :class:`ReviewOutputError` on failure."""
    stripped = text.strip()
    # Tolerate markdown code fences around the JSON.
    fence = _FENCE_RE.search(stripped)
    if fence:
        stripped = fence.group(1).strip()
    try:
        data: Any = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ReviewOutputError(f"output is not valid JSON: {exc}") from exc
    try:
        return ReviewPayload.model_validate(data)
    except ValidationError as exc:
        raise ReviewOutputError(f"output failed schema validation: {exc}") from exc


def payload_to_report(payload: ReviewPayload, repo_path: str) -> ReviewReport:
    return ReviewReport(
        repo_path=repo_path,
        findings=[f.to_finding() for f in payload.findings],
    )
