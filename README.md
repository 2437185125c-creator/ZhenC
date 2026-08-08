# CodeReview Harness

An automated **code review & fix agent** built on a lightweight, self-contained
**agent harness** — constraints, feedback loops, workflow control, and a
continuous-improvement eval loop (Harness Engineering).

`crh review` inspects the working-tree change of a git repo and produces a
structured report (AST static analysis + LLM review). `crh fix` then applies
fixes through a human-approved workflow, verifies with compile + tests, and
rolls back on failure. `crh eval` measures detection/fix rates on a planted-bug
suite.

## Highlights

- **Provider-agnostic harness** — the agent loop (`harness/loop.py`) only knows
  messages, tools and an `LLMProvider` protocol. Ships a deterministic mock and
  an OpenAI-compatible provider; run fully offline with `--static`.
- **Governance layer** (`governance/`) — sensitive-path denylist, read-only
  classification, review-scope enforcement (only changed files are writable),
  three permission modes, and human-in-the-loop approval gates.
- **Feedback loops** — tool results feed back into the loop; failed fix
  validation is fed back to the model for retry (bounded); JSON output-schema
  violations trigger a self-repair turn.
- **Explicit workflow control** (`workflow/`) — a strict state machine
  (PLAN→REVIEW→PROPOSE→APPROVE→APPLY→VALIDATE→REPORT), cross-stage step budget,
  and backup/rollback.
- **Evaluation loop** (`eval/`) — planted-bug fixture repos, detection/fix
  rates, regression failure log.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the pillar-by-pillar map.

## Quick start

```bash
uv sync --extra dev

# Offline deterministic review (no API key required)
uv run crh review --repo /path/to/repo --static

# Full LLM-driven review
export OPENAI_API_KEY=sk-...
uv run crh review --repo /path/to/repo --provider openai --model gpt-4o-mini

# Review + human-approved fix workflow (approves plan & each write)
uv run crh fix --repo /path/to/repo --provider openai

# Unattended fix (CI)
uv run crh fix --repo /path/to/repo --provider openai --auto-approve --mode full_auto

# Evaluation suite (offline, reproducible)
uv run crh eval
```

`--json` emits machine-readable reports; reports are written to `output/` by
default.

## Example report

```markdown
# Review Report — /tmp/crh-demo

**1 finding(s)**

## `net.py`

- **[medium]** `PY-MUTABLE-DEFAULT` `bug` :12 — Mutable default argument in process shared across calls.
  - suggestion: Use `None` and initialize inside the function.
```

## Package layout

```
src/code_review_harness/
├── harness/      # agent loop, messages, context budget, sync wrapper
├── llm/          # provider abstraction, mock, OpenAI-compatible provider
├── tools/        # tool registry + built-in tools (file/git/checks/write)
├── governance/   # permissions, modes, scope, approval gates, governed executor
├── review/       # diff parsing, AST static analysis, prompts/schema, pipeline
├── fix/          # snapshot/rollback, validation feedback loop, pipeline
├── workflow/     # state machine + top-level orchestrator
├── eval/         # planted-bug dataset, metrics, offline runner
└── cli.py        # `crh` command (sync wrapper around the async core)
```

## Development

```bash
uv run pytest        # 121 tests
uv run crh eval      # offline evaluation
```

## Reference

The `openharness/` directory is kept as a study reference for agent-harness
design (excluded from git).
