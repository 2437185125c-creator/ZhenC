"""Review pipeline — orchestrates one full review run.

Flow:
1. compute the change (diff + changed files + review scope)
2. run deterministic AST static analysis on the changed Python files
3. run the agent loop with the review prompts (LLM may use tools to inspect)
4. validate the model's JSON output against the schema; on failure, feed the
   validation error back to the model and retry (a harness feedback loop)
5. merge static + LLM findings into a :class:`ReviewReport`
"""

from __future__ import annotations

import logging
from pathlib import Path

from code_review_harness.governance.approval import auto_deny
from code_review_harness.governance.executor import GovernedToolExecutor
from code_review_harness.governance.modes import PermissionMode
from code_review_harness.governance.permissions import PermissionChecker
from code_review_harness.harness.loop import AgentLoop, EventSink
from code_review_harness.llm.base import LLMProvider
from code_review_harness.review.diff import build_scope, changed_files_from_repo, repo_diff_text
from code_review_harness.review.models import Finding, ReviewReport
from code_review_harness.review.prompts import build_review_system_prompt, build_review_user_prompt
from code_review_harness.review.schema import ReviewOutputError, parse_review_payload, payload_to_report
from code_review_harness.review.static_analyzer import analyze_source
from code_review_harness.tools import default_tool_registry

log = logging.getLogger(__name__)

MAX_JSON_REPAIR_ATTEMPTS = 1


class ReviewPipeline:
    """Runs the review agent against a repository and returns a structured report."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        cwd: Path,
        mode: PermissionMode = PermissionMode.DEFAULT,
        checker: PermissionChecker | None = None,
        max_turns: int | None = 12,
        on_event: EventSink | None = None,
    ) -> None:
        self._provider = provider
        self._cwd = Path(cwd).resolve()
        self._registry = default_tool_registry()
        self._checker = checker or PermissionChecker(mode=mode)
        self._mode = mode
        self._max_turns = max_turns
        self._on_event = on_event

    async def review(self, repo_path: Path | None = None) -> ReviewReport:
        repo = Path(repo_path or self._cwd).resolve()

        changed_files = await changed_files_from_repo(repo)
        scope = build_scope(repo, changed_files)
        self._checker.set_scope(scope)
        log.debug("review scope: %d changed files", len(changed_files))

        static_findings = self._run_static_analysis(repo, changed_files)
        diff_text = await repo_diff_text(repo)
        changed_names = [str(f.path) for f in changed_files if f.status != "D"]

        loop = AgentLoop(
            provider=self._provider,
            tool_registry=self._registry,
            executor=GovernedToolExecutor(
                tool_registry=self._registry,
                checker=self._checker,
                cwd=repo,
                approval_gate=auto_deny,
                event_sink=self._on_event,
            ),
            system_prompt=build_review_system_prompt(),
            cwd=repo,
            max_turns=self._max_turns,
            on_event=self._on_event,
        )

        user_prompt = build_review_user_prompt(
            repo_path=str(repo),
            diff_text=diff_text,
            static_findings=static_findings,
            changed_file_names=changed_names,
        )
        result = await loop.run(user_prompt)
        payload, error = await self._extract_with_repair(loop, result.final_text)
        if error is not None:
            raise ReviewOutputError(
                f"model output could not be parsed after {MAX_JSON_REPAIR_ATTEMPTS} repair(s): {error}"
            )

        report = payload_to_report(payload, str(repo))
        report.findings = _merge_findings(static_findings, report.findings)
        report.notes.append(
            f"static analysis: {len(static_findings)} finding(s); "
            f"model: {len(payload.findings)} finding(s)"
        )
        return report

    def _run_static_analysis(self, repo: Path, changed_files) -> list[Finding]:
        findings: list[Finding] = []
        for changed in changed_files:
            if not changed.is_python or changed.status == "D":
                continue
            path = repo / changed.path
            if path.exists():
                try:
                    source = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                findings.extend(analyze_source(source, str(changed.path)))
        return findings

    async def _extract_with_repair(self, loop: AgentLoop, final_text: str):
        """Parse the model's JSON; on failure, feed the error back and retry."""
        for attempt in range(MAX_JSON_REPAIR_ATTEMPTS + 1):
            try:
                return parse_review_payload(final_text), None
            except ReviewOutputError as exc:
                if attempt >= MAX_JSON_REPAIR_ATTEMPTS:
                    return None, str(exc)
                log.debug("review JSON invalid, requesting repair: %s", exc)
                repaired = await loop.continue_run(
                    "Your previous response was not valid JSON. Validation error:\n"
                    f"{exc}\n\n"
                    "Respond with the corrected JSON report only — no prose, no markdown fences."
                )
                final_text = repaired.final_text
        return None, "unreachable"


def _merge_findings(static: list[Finding], model: list[Finding]) -> list[Finding]:
    """Merge static and model findings, de-duplicating by rule+file+line."""
    merged = list(model)
    seen = {(f.rule_id, f.file_path, f.line) for f in model}
    for finding in static:
        key = (finding.rule_id, finding.file_path, finding.line)
        if key not in seen:
            merged.append(finding)
            seen.add(key)
    return merged
