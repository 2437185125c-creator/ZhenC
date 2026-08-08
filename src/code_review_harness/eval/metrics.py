"""Metrics for the evaluation loop.

The eval reports three headline numbers:
- detection rate:  fraction of planted bugs the reviewer found
- fix rate:        fraction of detected bugs the fixer resolved (validation green)
- avg findings:    average number of reported findings per case (noise gauge)

Every failing case is also written to a JSONL log so failures can be replayed
and regressions caught when prompts or analyzers change.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class CaseResult:
    name: str
    description: str
    expected_rule: str
    detected: bool
    fixed: bool = False
    findings_count: int = 0
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None or not self.detected or not self.fixed


@dataclass
class EvalSummary:
    total: int = 0
    detected: int = 0
    fixed: int = 0
    results: list[CaseResult] = field(default_factory=list)

    @property
    def detection_rate(self) -> float:
        return _ratio(self.detected, self.total)

    @property
    def fix_rate(self) -> float:
        return _ratio(self.fixed, self.detected)

    @property
    def avg_findings(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.findings_count for r in self.results) / len(self.results)

    def failed_cases(self) -> list[CaseResult]:
        return [r for r in self.results if r.failed]

    def summary_dict(self) -> dict:
        return {
            "total": self.total,
            "detected": self.detected,
            "fixed": self.fixed,
            "detection_rate": round(self.detection_rate, 3),
            "fix_rate": round(self.fix_rate, 3),
            "avg_findings": round(self.avg_findings, 2),
        }

    def write_failures(self, out_dir: Path) -> Path:
        """Append every failed case to ``failures.jsonl`` (one JSON per line)."""
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "failures.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            for result in self.failed_cases():
                handle.write(json.dumps(asdict(result)) + "\n")
        return log_path


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
