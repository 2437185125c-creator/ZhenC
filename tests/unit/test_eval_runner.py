"""Integration tests for the offline eval runner."""
from __future__ import annotations

import pytest

from code_review_harness.eval.dataset import default_dataset
from code_review_harness.eval.runner import ScriptedFixer, StaticReviewer, run_eval


@pytest.mark.asyncio
async def test_offline_eval_detects_all_planted_bugs(tmp_path):
    summary = await run_eval(
        default_dataset(),
        reviewer=StaticReviewer(),
        fixer=ScriptedFixer(),
        work_dir=tmp_path,
    )

    assert summary.total == len(default_dataset())
    # The deterministic static analyzer should catch every planted bug.
    assert summary.detection_rate == 1.0
    assert summary.fix_rate == 1.0


@pytest.mark.asyncio
async def test_offline_eval_writes_failure_log(tmp_path):
    summary = await run_eval(
        default_dataset(),
        reviewer=StaticReviewer(),
        fixer=ScriptedFixer(),
        work_dir=tmp_path,
    )
    log_path = summary.write_failures(tmp_path / "out")
    if not summary.failed_cases():
        # All pass -> log file may be empty but should still be created.
        assert log_path.exists()
    else:
        assert log_path.stat().st_size > 0


@pytest.mark.asyncio
async def test_eval_returns_reproducible_summary(tmp_path):
    first = await run_eval(
        default_dataset(),
        reviewer=StaticReviewer(),
        fixer=ScriptedFixer(),
        work_dir=tmp_path / "run1",
    )
    second = await run_eval(
        default_dataset(),
        reviewer=StaticReviewer(),
        fixer=ScriptedFixer(),
        work_dir=tmp_path / "run2",
    )
    assert first.summary_dict() == second.summary_dict()
