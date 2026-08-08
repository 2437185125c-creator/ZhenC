"""Command-line interface: ``crh review | fix | eval``.

The CLI is the synchronous face of the harness: it parses args, builds the
async pipelines and drives them through :func:`run_async`.  ``--static`` makes
review work fully offline via the AST analyzer (no API key required).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from code_review_harness.eval.dataset import default_dataset
from code_review_harness.eval.runner import ScriptedFixer, StaticReviewer, run_eval
from code_review_harness.governance.approval import auto_approve, console_approval
from code_review_harness.governance.modes import PermissionMode
from code_review_harness.harness.sync import run_async
from code_review_harness.review.pipeline import ReviewPipeline
from code_review_harness.review.reporting import to_json, to_markdown
from code_review_harness.workflow.workflow import ReviewWorkflow

DEFAULT_OUTPUT_DIR = "output"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crh",
        description="CodeReview Harness — automated code review & fix agent.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=".", help="Repository root (default: current dir).")
    common.add_argument("--mode", choices=[m.value for m in PermissionMode], default="default")
    common.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    common.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Where to write reports.")

    sub = parser.add_subparsers(dest="command", required=True)

    review = sub.add_parser("review", parents=[common], help="Review the working-tree change.")
    review.add_argument("--static", action="store_true", help="Use only the deterministic AST analyzer (offline).")
    review.add_argument("--provider", choices=["openai", "mock"], default="openai")
    review.add_argument("--model", default="gpt-4o-mini")
    review.add_argument("--base-url", default="https://api.openai.com/v1")
    review.add_argument("--api-key", default=None)
    review.add_argument("--max-turns", type=int, default=12)

    fix = sub.add_parser("fix", parents=[common], help="Review then (with approval) fix findings.")
    fix.add_argument("--provider", choices=["openai", "mock"], default="openai")
    fix.add_argument("--model", default="gpt-4o-mini")
    fix.add_argument("--base-url", default="https://api.openai.com/v1")
    fix.add_argument("--api-key", default=None)
    fix.add_argument("--max-turns", type=int, default=12)
    fix.add_argument("--max-attempts", type=int, default=3)
    fix.add_argument("--auto-approve", action="store_true", help="Skip interactive approvals.")

    eval_parser = sub.add_parser("eval", parents=[common], help="Run the offline evaluation suite.")
    eval_parser.add_argument("--work-dir", default="eval-results", help="Working dir for case repos.")
    return parser


def _provider(args) -> "object":
    from code_review_harness.llm.base import LLMProvider
    from code_review_harness.llm.mock_provider import MockProvider
    from code_review_harness.llm.openai_compat import OpenAICompatProvider

    if args.provider == "mock":
        return MockProvider([])
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "No API key. Set OPENAI_API_KEY or pass --api-key/--base-url, "
            "or use `crh review --static` for an offline review."
        )
    return OpenAICompatProvider(api_key=api_key, base_url=args.base_url, model=args.model)


def _mode(args) -> PermissionMode:
    return PermissionMode(args.mode)


async def _static_review(repo: Path):
    return await StaticReviewer().review(repo)


async def _llm_review(repo: Path, args):
    pipeline = ReviewPipeline(
        provider=_provider(args),
        cwd=repo,
        mode=_mode(args),
        max_turns=args.max_turns,
    )
    return await pipeline.review()


def _write_output(repo: Path, args, *, markdown: str, json_text: str) -> None:
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = repo.name or "repo"
    (out / f"{stem}-report.md").write_text(markdown, encoding="utf-8")
    (out / f"{stem}-report.json").write_text(json_text, encoding="utf-8")


def cmd_review(args) -> int:
    repo = Path(args.repo).resolve()
    report = run_async(_static_review(repo) if args.static else _llm_review(repo, args))

    markdown = to_markdown(report)
    json_text = to_json(report)
    if args.output_dir:
        _write_output(repo, args, markdown=markdown, json_text=json_text)
    if args.json:
        print(json_text)
    else:
        print(f"reviewed {repo}\n")
        print(markdown)
    return 0


def cmd_fix(args) -> int:
    repo = Path(args.repo).resolve()
    plan_gate = auto_approve if args.auto_approve else console_approval
    tool_gate = auto_approve if (args.auto_approve or args.mode == "full_auto") else console_approval
    workflow = ReviewWorkflow(
        provider=_provider(args),
        cwd=repo,
        mode=_mode(args),
        plan_approval=plan_gate,
        tool_approval=tool_gate,
        max_fix_attempts=args.max_attempts,
        max_turns=args.max_turns,
    )
    result = run_async(workflow.run())

    markdown = to_markdown(result.report) if result.report else "no report"
    if args.output_dir:
        _write_output(
            repo,
            args,
            markdown=markdown,
            json_text=to_json(result.report) if result.report else "{}",
        )
    summary = (
        f"plan_approved={result.plan_approved} "
        f"fix_success={result.fix.success if result.fix else 'n/a'} "
        f"final_stage={result.final_stage.value}\n"
        + result.fix.validation_output[-400:]
        if result.fix
        else f"final_stage={result.final_stage.value} (no fix run)\n"
    )
    if args.json:
        print(to_json(result.report) if result.report else "{}")
    else:
        print(f"workflow: {summary}\n")
        print(markdown)
    return 0 if result.succeeded else 1


def cmd_eval(args) -> int:
    work_dir = Path(args.work_dir)
    summary = run_async(
        run_eval(
            default_dataset(),
            reviewer=StaticReviewer(),
            fixer=ScriptedFixer(),
            work_dir=work_dir,
        )
    )
    summary.write_failures(work_dir)
    print(summary.summary_dict())
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "review":
            return cmd_review(args)
        if args.command == "fix":
            return cmd_fix(args)
        if args.command == "eval":
            return cmd_eval(args)
    except SystemExit as exc:
        # Provider setup failures (e.g. missing API key) surface as SystemExit.
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        return exc.code if isinstance(exc.code, int) else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
