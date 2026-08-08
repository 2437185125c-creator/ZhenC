# Architecture

CodeReview Harness is an automated **code review & fix agent** built on a
self-contained agent harness. This document explains the design in terms of
the four Harness Engineering pillars it implements.

## Harness pillars → implementation map

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CONSTRAINT MECHANISMS (约束机制)                                        │
│  governance/                                                             │
│   • PermissionChecker: sensitive-path denylist, tool allow/deny lists,   │
│     path & command rules — evaluation order is explicit (first-match)    │
│   • ReviewScope: the agent may only WRITE to files in the diff           │
│   • modes: default (ask) / plan (no writes) / full_auto (run freely)     │
│   • tools declare read_only; input validated by pydantic before running  │
│  review/schema.py: model output must validate against ReviewPayload      │
│  harness/context.py: context-budget truncation (oldest-first)            │
├──────────────────────────────────────────────────────────────────────────┤
│  FEEDBACK LOOPS (反馈回路)                                                │
│  harness/loop.py: model → tools → results back into history → next turn  │
│  fix/validator.py: apply fix → compile + pytest → failure output is fed  │
│      back to the model for another attempt (up to max_fix_attempts)      │
│  review/pipeline.py: JSON schema validation failure triggers one repair  │
│      turn telling the model exactly why its output was rejected          │
├──────────────────────────────────────────────────────────────────────────┤
│  WORKFLOW CONTROL (工作流控制)                                            │
│  workflow/state_machine.py: strict FSM (PLAN→REVIEW→PROPOSE→APPROVE→     │
│      APPLY→VALIDATE→REPORT), invalid transitions rejected                 │
│  workflow/workflow.py: plan-level human approval gate before applying    │
│  governance/approval.py: tool-level HITL gate (console / auto in tests)  │
│  workflow/state_machine.py: WorkflowBudget caps total tool executions    │
│  harness/loop.py: max_turns per stage                                    │
│  fix/applier.py: backup/rollback safety net                              │
├──────────────────────────────────────────────────────────────────────────┤
│  CONTINUOUS IMPROVEMENT LOOP (持续改进循环)                               │
│  eval/dataset.py: planted-bug fixture repos (one bug each, with a        │
│      failing test; the fix is the known-good version)                    │
│  eval/metrics.py: detection_rate / fix_rate / avg_findings               │
│  eval/runner.py: failure cases written to failures.jsonl for regression  │
│  cli: `crh eval` runs the suite reproducibly                             │
└──────────────────────────────────────────────────────────────────────────┘
```

## Module dependencies

The dependency graph is strictly layered — `review` and `fix` do not import
each other; both are orchestrated by `workflow`.

```
workflow ──► review ──► governance
      │            │
      └────► fix ──┴──► tools ──► harness ──► llm
                  ▲
                  └──────────► utils
```

- `harness` — provider-agnostic agent loop, messages, context budget, sync wrapper.
  Knows nothing about code review.
- `llm` — `LLMProvider` abstraction, deterministic `MockProvider`, OpenAI-compatible
  provider. Only depends on `harness`.
- `tools` — `BaseTool`/`ToolRegistry`, read-only tools (read_file, grep, git_*),
  mutating tool (write_file), validation tool (run_checks). Depends on `harness`+`utils`.
- `governance` — permission checker, modes, review scope, approval gate, governed
  executor wrapping tool execution. Depends on `tools`+`harness`.
- `review` — diff parsing, AST static analysis, review prompts/schema, review
  pipeline. Depends on `governance`+`tools`+`harness`.
- `fix` — snapshot/rollback, fix prompts, validation, fix pipeline. Depends on
  `governance`+`review` (for the report model)+`tools`.
- `workflow` — FSM + top-level orchestrator wiring review and fix together.
- `eval` — dataset, metrics, offline runner. Depends on `review`+`fix`.

## Data flow of a full run (`crh fix`)

```
                ┌─ PLAN ─┐
                ▼        │
             REVIEW ◄────┤ (scope = changed files)
                │        │
                ▼        │
            PROPOSE      │
                │        │
                ▼        │
   ┌──────► APPROVE ──no─┘ (human approves the fix plan)
   │ yes     │
   │         ▼
   │       APPLY ──► write_file (tool-level approval in default mode)
   │         │
   │         ▼
   │     VALIDATE ──fail──► feedback loop: retry up to N, else ROLLBACK
   │         │ pass
   │         ▼
   └────── REPORT ──► DONE
```

## Key design decisions

1. **The loop is generic; the domain lives in tools and prompts.** `AgentLoop`
   only knows messages, providers and a `ToolExecutor` protocol. Reviewing and
   fixing are expressed as tool sets + system prompts. Governance plugs in by
   wrapping the executor — the loop never changes.
2. **Output contracts are enforced, not requested.** The review model must emit
   JSON matching `ReviewPayload`; invalid output is fed back as an error (a
   feedback loop), not silently tolerated.
3. **Deterministic parts carry the guarantee; the LLM carries the judgment.**
   The AST analyzer finds issues with zero false positives on the eval suite;
   the LLM finds deeper, context-dependent issues. Static findings are merged
   into the report.
4. **Rollback is a first-class harness feature.** Every file the fix agent may
   touch is snapshotted before the run; failed validation restores it.
