"""Evaluation loop: dataset, metrics, runner."""

from code_review_harness.eval.dataset import BugCase, default_dataset
from code_review_harness.eval.metrics import CaseResult, EvalSummary
from code_review_harness.eval.runner import (
    FixOutcome,
    Fixer,
    Reviewer,
    ScriptedFixer,
    StaticReviewer,
    run_eval,
)

__all__ = [
    "BugCase",
    "CaseResult",
    "EvalSummary",
    "FixOutcome",
    "Fixer",
    "Reviewer",
    "ScriptedFixer",
    "StaticReviewer",
    "default_dataset",
    "run_eval",
]
