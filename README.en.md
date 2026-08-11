# CodeReview Harness

[English](README.en.md) · [简体中文](README.md)

An automated **code review & fix agent** built on a lightweight, self-contained
**agent harness** — constraints, feedback loops, workflow control, and a
continuous-improvement eval loop (Harness Engineering).

`crh review` inspects the working-tree change of a git repo and produces a
structured report (AST static analysis + LLM review). `crh fix` applies fixes
through a human-approved workflow, verifies with compile + tests, and rolls back
on failure. `crh eval` measures detection/fix rates on a planted-bug suite.

## Highlights

- **Provider-agnostic harness** — the agent loop (`harness/loop.py`) only knows
  messages, tools and an `LLMProvider` protocol. Ships a deterministic mock and
  an OpenAI/DeepSeek-compatible provider; run fully offline with `--static`.
- **Governance layer** (`governance/`) — sensitive-path denylist, read-only
  classification, review-scope enforcement (only changed files are writable),
  three permission modes, and human-in-the-loop approval gates.
- **Inspect-first constraint** — the review model MUST call a tool before
  reporting; a report produced without inspecting the code is rejected and the
  model is told to go back and look.
- **Feedback loops** — tool results feed back into the loop; failed fix
  validation is fed back to the model for retry (bounded); JSON output-schema
  violations trigger a self-repair turn.
- **Explicit workflow control** (`workflow/`) — a strict state machine
  (PLAN→REVIEW→PROPOSE→APPROVE→APPLY→VALIDATE→REPORT), cross-stage step budget,
  and backup/rollback.
- **Evaluation loop** (`eval/`) — planted-bug fixture repos, detection/fix
  rates, regression failure log.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the pillar-by-pillar map.

## Requirements

- Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/)
- The repo under review must be a **git repository** (crh reviews git working-tree changes)

## Install & configure the API key

```bash
uv sync --extra dev

# Install crh as a global command (works from any directory)
uv tool install --editable .

# Configure the API key once — crh reads it from (highest priority first):
#   --api-key <key>            command line
#   --env-file <path>          explicit .env file
#   API_KEY / OPENAI_API_KEY   environment variable
#   .env in the current dir    project-level
#   ~/.crh/.env                user-level (recommended, works everywhere)
mkdir -p ~/.crh && echo "API_KEY=sk-..." > ~/.crh/.env
```

New terminals pick up the key automatically. To verify: `crh review --static`
(offline, no key needed) or any LLM command prints `[crh] using API key from ...`.

## Quick start

```bash
# Offline deterministic review (no API key required)
crh review --repo /path/to/repo --static

# Full LLM-driven review (defaults to DeepSeek)
crh review --repo /path/to/repo

# Review + human-approved fix workflow (approves the plan & each write)
crh fix --repo /path/to/repo

# Unattended fix (CI)
crh fix --repo /path/to/repo --auto-approve --mode full_auto

# Evaluation suite (offline, reproducible)
crh eval
```

`--json` emits machine-readable reports; reports are written to `output/` by
default.

## Live validation

Run against a real repo with a planted change, the DeepSeek-driven loop found —
in addition to the AST analyzer — a **SQL injection** (critical), a lost
monetary rounding, and a swallowed-exception `NameError`, demonstrating that the
LLM + static-analysis combination catches issues neither can find alone.

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
├── llm/          # provider abstraction, mock, OpenAI/DeepSeek-compatible provider
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
uv run pytest        # 134 tests
uv run crh eval      # offline evaluation (6 planted-bug cases, detection/fix 0.7)
```

## Reference

The `openharness/` directory is kept as a study reference for agent-harness
design (excluded from git).
