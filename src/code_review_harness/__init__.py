"""CodeReview Harness — an automated code review & fix agent built on a lightweight agent harness.

The package is split into high-cohesion modules:

- ``harness``: provider-agnostic agent loop (messages, hooks, context budget)
- ``llm``:   LLM provider abstraction + deterministic mock
- ``tools``: tool registry and built-in tools
- ``governance``: permission checking, modes, human approval gate
- ``review``: diff parsing, static analysis, review models & prompts
- ``fix``:   patch application and validation feedback loop
- ``workflow``: state machine tying the stages together
- ``eval``:  evaluation dataset, metrics, regression runner
"""

from code_review_harness.harness.messages import Message, ToolResult, ToolUse

__all__ = ["Message", "ToolResult", "ToolUse"]
__version__ = "0.1.0"
