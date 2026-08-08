"""Deterministic in-process LLM provider for tests and offline demos.

The mock replays a pre-scripted list of :class:`LLMResponse` objects and
records every :class:`LLMRequest` it receives, so tests can assert both the
harness's *output* and the exact *input* it fed the model each turn.
"""

from __future__ import annotations

from code_review_harness.llm.base import LLMProvider, LLMRequest, LLMResponse


class MockProviderExhausted(RuntimeError):
    """Raised when the agent loop requests more turns than the script provides."""


class MockProvider(LLMProvider):
    """Replays a scripted conversation against the harness loop."""

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self._responses = list(responses or [])
        self._cursor = 0
        self.requests: list[LLMRequest] = []

    @property
    def remaining(self) -> int:
        return len(self._responses) - self._cursor

    @property
    def cursor(self) -> int:
        return self._cursor

    def reset(self) -> None:
        self._cursor = 0
        self.requests.clear()

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self._cursor >= len(self._responses):
            raise MockProviderExhausted(
                f"script exhausted after {len(self._responses)} response(s); "
                "the agent loop requested another turn"
            )
        response = self._responses[self._cursor]
        self._cursor += 1
        return response
