"""Evaluation runner.

The runner is provider-agnostic: it takes any ``reviewer`` (async
repo -> ReviewReport) and ``fixer`` (async case/report/repo -> FixResult).
Two deterministic implementations ship out of the box for offline use:

- :class:`StaticReviewer` — the AST static analyzer (no LLM)
- :class:`ScriptedFixer`  — applies the known-good content when the expected
  rule was detected (used to exercise the eval loop reproducibly)

Swap in a real LLM-backed reviewer/fixer (e.g. the :class:`ReviewWorkflow`)
to evaluate the full agent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from code_review_harness.eval.dataset import BugCase
from code_review_harness.eval.metrics import CaseResult, EvalSummary
from code_review_harness.fix.applier import ChangeSet
from code_review_harness.fix.validator import validate_fix
from code_review_harness.review.diff import changed_files_from_repo
from code_review_harness.review.models import ReviewReport
from code_review_harness.review.static_analyzer import analyze_source

log = logging.getLogger(__name__)


class Reviewer(Protocol):
    async def review(self, repo: Path) -> ReviewReport: ...


class Fixer(Protocol):
    async def fix(self, case: BugCase, report: ReviewReport, repo: Path) -> "FixOutcome": ...


@dataclass
class FixOutcome:
    success: bool
    output: str = ""


class StaticReviewer:
    """Offline reviewer: deterministic AST analysis of the changed files."""

    async def review(self, repo: Path) -> ReviewReport:
        changed = await changed_files_from_repo(repo)
        findings = []
        for changed_file in changed:
            if not changed_file.is_python or changed_file.status == "D":
                continue
            path = repo / changed_file.path
            if path.exists():
                try:
                    source = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                findings.extend(analyze_source(source, str(changed_file.path)))
        return ReviewReport(repo_path=str(repo), findings=findings)


class ScriptedFixer:
    """Offline fixer: applies the known-good content if the expected rule fired."""

    async def fix(self, case: BugCase, report: ReviewReport, repo: Path) -> FixOutcome:
        detected = any(f.rule_id == case.expected_rule for f in report.findings)
        if not detected:
            return FixOutcome(success=False, output=f"expected rule {case.expected_rule} not detected")
        target = repo / case.filename
        changeset = ChangeSet(root=repo)
        changeset.backup(target)
        target.write_text(case.correct, encoding="utf-8")
        changeset.detect_writes()
        validation = await validate_fix(repo, changeset.changed_python_files())
        if not validation.success:
            changeset.rollback()
        return FixOutcome(success=validation.success, output=validation.output)


async def run_eval(
    dataset: list[BugCase],
    *,
    reviewer: Reviewer,
    fixer: Fixer,
    work_dir: Path,
) -> EvalSummary:
    """Run every case through review+fix and aggregate the metrics."""
    summary = EvalSummary()
    for case in dataset:
        repo = case.build(work_dir / "cases")
        result = CaseResult(
            name=case.name,
            description=case.description,
            expected_rule=case.expected_rule,
            detected=False,
        )
        try:
            report = await reviewer.review(repo)
            result.findings_count = report.count
            result.detected = any(f.rule_id == case.expected_rule for f in report.findings)
            if result.detected:
                outcome = await fixer.fix(case, report, repo)
                result.fixed = outcome.success
                if not outcome.success:
                    result.error = f"fix failed: {outcome.output[-200:]}"
        except Exception as exc:  # noqa: BLE001 — eval must not die on one case
            result.error = f"{type(exc).__name__}: {exc}"
            log.exception("eval case %s raised", case.name)

        summary.results.append(result)
        summary.total += 1
        summary.detected += int(result.detected)
        summary.fixed += int(result.fixed)

    return summary
