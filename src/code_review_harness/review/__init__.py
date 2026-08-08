"""Code review domain: models, diff parsing, static analysis, prompts, pipeline."""

from code_review_harness.review.diff import ChangedFile, DiffHunk, build_scope, changed_files_from_repo, parse_diff
from code_review_harness.review.models import Finding, FindingCategory, ReviewReport, Severity
from code_review_harness.review.pipeline import ReviewPipeline
from code_review_harness.review.reporting import to_json, to_markdown
from code_review_harness.review.schema import ReviewOutputError, parse_review_payload, payload_to_report
from code_review_harness.review.static_analyzer import analyze_file, analyze_source

__all__ = [
    "ChangedFile",
    "DiffHunk",
    "Finding",
    "FindingCategory",
    "ReviewOutputError",
    "ReviewPipeline",
    "ReviewReport",
    "Severity",
    "analyze_file",
    "analyze_source",
    "build_scope",
    "changed_files_from_repo",
    "parse_diff",
    "parse_review_payload",
    "payload_to_report",
    "to_json",
    "to_markdown",
]
