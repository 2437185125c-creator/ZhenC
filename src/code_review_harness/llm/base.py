"""LLM provider abstraction.

A provider converts the harness's provider-agnostic ``Message`` history into
its own wire format and streams back a structured :class:`LLMResponse`
containing optional tool invocations.  This interface is the seam that lets
the harness run against any vendor (or a deterministic mock).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from code_review_harness.harness.messages import Message, ToolSpec, ToolUse


@dataclass(frozen=True)
class LLMRequest:
    """Everything the harness sends to a provider for one model turn."""

    messages: tuple[Message, ...]
    system_prompt: str
    tools: tuple[ToolSpec, ...] = ()
    max_tokens: int = 4096


@dataclass(frozen=True)
class LLMResponse:
    """Structured reply from a provider.

    Either ``text`` (the model stopped with prose), ``tool_uses`` (the model
    asked to call tools), or both.
    """

    text: str = ""
    tool_uses: tuple[ToolUse, ...] = ()

    @property
    def wants_tool_use(self) -> bool:
        return bool(self.tool_uses)


class LLMProvider(ABC):
    """Base class for LLM backends."""

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Return the model's reply for a single request.

        The harness calls this repeatedly (each iteration feeds prior tool
        results back through ``request.messages``) until the model stops
        requesting tools or the step budget is exhausted.
        """
        raise NotImplementedError
