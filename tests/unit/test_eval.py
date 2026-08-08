"""Tests for the eval dataset and metrics."""
from __future__ import annotations

from pathlib import Path

from code_review_harness.eval.dataset import BugCase, default_dataset
from code_review_harness.eval.metrics import CaseResult, EvalSummary
from code_review_harness.review.static_analyzer import analyze_source


def test_build_creates_repo_with_planted_bug(tmp_path):
    case = default_dataset()[0]
    repo = case.build(tmp_path)
    # A git repo exists with the baseline committed and the bug in the working tree.
    assert (repo / case.filename).exists()
    assert "except:" in (repo / case.filename).read_text(encoding="utf-8")


def test_default_dataset_has_expected_rules():
    rules = {c.expected_rule for c in default_dataset()}
    assert {
        "PY-BARE-EXCEPT",
        "PY-MUTABLE-DEFAULT",
        "PY-IS-LITERAL",
        "PY-UNDEFINED-NAME",
        "PY-DANGEROUS-CALL",
        "PY-SYNTAX",
    } <= rules


def test_each_buggy_source_triggers_its_expected_rule():
    for case in default_dataset():
        findings = analyze_source(case.buggy, case.filename)
        rule_ids = {f.rule_id for f in findings}
        assert case.expected_rule in rule_ids, f"{case.name} did not trigger {case.expected_rule}"


def test_each_correct_source_does_not_trigger_rule():
    # The fixed version should not fire the planted-bug rule.
    for case in default_dataset():
        findings = analyze_source(case.correct, case.filename)
        rule_ids = {f.rule_id for f in findings}
        assert case.expected_rule not in rule_ids, f"{case.name} still triggers {case.expected_rule}"


def test_metrics_rates():
    summary = EvalSummary(total=4, detected=3, fixed=2)
    assert round(summary.detection_rate, 3) == 0.75
    assert round(summary.fix_rate, 3) == 0.667


def test_failures_jsonl_roundtrip(tmp_path):
    summary = EvalSummary(total=1, detected=1, fixed=0)
    summary.results = [
        CaseResult(
            name="case1",
            description="desc",
            expected_rule="PY-X",
            detected=True,
            fixed=False,
            findings_count=2,
            error="fix failed",
        )
    ]
    log_path = summary.write_failures(tmp_path)
    assert log_path.exists()
    import json

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["name"] == "case1"
