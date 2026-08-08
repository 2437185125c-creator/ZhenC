"""Unit tests for the review output schema and JSON parsing."""
from __future__ import annotations

import pytest

from code_review_harness.review.schema import (
    ReviewOutputError,
    ReviewPayload,
    parse_review_payload,
    payload_to_report,
)
from code_review_harness.review.models import Severity


VALID_JSON = """{
  "findings": [
    {
      "rule_id": "REVIEW-1",
      "category": "bug",
      "severity": "high",
      "file_path": "app.py",
      "line": 12,
      "message": "Off-by-one error",
      "suggestion": "Use len(x) - 1"
    }
  ],
  "summary": "One bug found."
}"""


def test_parse_valid_json():
    payload = parse_review_payload(VALID_JSON)
    assert len(payload.findings) == 1
    assert payload.findings[0].file_path == "app.py"
    assert payload.findings[0].severity == Severity.HIGH
    assert payload.summary == "One bug found."


def test_parse_tolerates_markdown_fence():
    payload = parse_review_payload(f"Here is the report:\n```json\n{VALID_JSON}\n```")
    assert len(payload.findings) == 1


def test_parse_rejects_non_json():
    with pytest.raises(ReviewOutputError):
        parse_review_payload("this is not json")


def test_parse_rejects_schema_violation():
    with pytest.raises(ReviewOutputError):
        parse_review_payload('{"findings": [{"severity": "not-a-severity"}]}')


def test_payload_to_report():
    payload = parse_review_payload(VALID_JSON)
    report = payload_to_report(payload, "/tmp/repo")
    assert report.repo_path == "/tmp/repo"
    assert report.count == 1
    assert report.findings[0].suggestion is not None
