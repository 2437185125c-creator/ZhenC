"""The agent loop — the heart of the harness.

Each iteration:  send history to the provider → if the model requested tools,
validate + execute them and feed results back → repeat until the model stops
requesting tools or the turn budget is exhausted.

The loop is deliberately provider-agnostic and tool-agnostic.  Governance
(permissions, approval) plugs in later by wrapping tool execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from code_review_harness.harness.context import truncate_history
from code_review_harness.harness.messages import Message, ToolResult, ToolUse
from code_review_harness.llm.base import LLMProvider, LLMRequest
from code_review_harness.tools.base import ToolRegistry

log = logging.getLogger(__name__)

# Callback shape: async fn(event_name: str, payload: dict) -> None
EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]


class ToolExecutor(Protocol):
    """Seam through which the loop executes tools.

    The raw :class:`SimpleToolExecutor` just runs tools; the governance layer
    wraps it to enforce permissions and ask for approval.  The loop never sees
    the difference.
    """

    async def execute(self, tool_use: ToolUse) -> ToolResult: ...


class MaxTurnsExceeded(RuntimeError):
    """Raised when the loop exceeds the configured turn budget."""

    def __init__(self, max_turns: int) -> None:
        super().__init__(f"Exceeded maximum turn limit ({max_turns})")
        self.max_turns = max_turns


@dataclass(frozen=True)
class AgentResult:
    """Outcome of a single ``run`` call."""

    messages: tuple[Message, ...] = field(default_factory=tuple)
    final_text: str = ""
    turns: int = 0


class AgentLoop:
    """Runs the model/tool iteration until the model stops or the budget runs out."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        tool_registry: ToolRegistry,
        executor: ToolExecutor,
        system_prompt: str,
        cwd: Path,
        max_turns: int | None = 8,
        max_tokens: int = 4096,
        context_budget_chars: int | None = None,
        on_event: EventSink | None = None,
    ) -> None:
        self._provider = provider
        self._tool_registry = tool_registry
        self._executor = executor
        self._system_prompt = system_prompt
        self._cwd = Path(cwd).resolve()
        self._max_turns = max_turns
        self._max_tokens = max_tokens
        self._context_budget_chars = context_budget_chars
        self._on_event = on_event
        self._history: list[Message] = []
        self._turns = 0

    async def _emit(self, name: str, payload: dict[str, Any]) -> None:
        if self._on_event is not None:
            await self._on_event(name, payload)

    async def run(self, user_text: str) -> AgentResult:
        """Start a fresh conversation with ``user_text`` and iterate to a final answer."""
        self._history = [Message.user(user_text)]
        self._turns = 0
        return await self._iterate()

    async def continue_run(self, follow_up: str) -> AgentResult:
        """Continue the existing conversation with a follow-up message.

        Used for feedback loops — e.g. telling the model its JSON output failed
        validation and to retry, while keeping all prior tool results in context.
        """
        self._history.append(Message.user(follow_up))
        return await self._iterate()

    async def _iterate(self) -> AgentResult:
        while True:
            if self._max_turns is not None and self._turns >= self._max_turns:
                raise MaxTurnsExceeded(self._max_turns)
            self._turns += 1

            request = LLMRequest(
                messages=tuple(self._history),
                system_prompt=self._system_prompt,
                tools=self._tool_registry.specs(),
                max_tokens=self._max_tokens,
            )
            response = await self._provider.generate(request)

            self._history.append(Message.assistant(response.text, response.tool_uses))
            await self._emit(
                "assistant_message",
                {"text": response.text, "tool_uses": [u.name for u in response.tool_uses]},
            )

            if not response.wants_tool_use:
                await self._emit("stop", {"turns": self._turns})
                return AgentResult(
                    messages=tuple(self._history),
                    final_text=response.text,
                    turns=self._turns,
                )

            tool_results = await self._execute_tools(response.tool_uses)
            self._history.append(Message.of_tool_results(tool_results))

            if self._context_budget_chars is not None:
                self._history = truncate_history(self._history, self._context_budget_chars)

    async def _execute_tools(self, tool_uses: tuple[ToolUse, ...]) -> list[ToolResult]:
        results: list[ToolResult] = []
        for use in tool_uses:
            await self._emit(
                "tool_execution_started",
                {"tool": use.name, "input": use.input},
            )
            result = await self._executor.execute(use)
            results.append(result)
            await self._emit(
                "tool_execution_completed",
                {"tool": use.name, "is_error": result.is_error, "output": result.output[:200]},
            )
        return results
