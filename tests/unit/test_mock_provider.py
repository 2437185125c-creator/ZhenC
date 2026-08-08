"""Unit tests for the deterministic mock LLM provider."""
from __future__ import annotations

import pytest

from code_review_harness.harness.messages import Message, ToolUse
from code_review_harness.llm.base import LLMRequest, LLMResponse
from code_review_harness.llm.mock_provider import MockProvider, MockProviderExhausted


@pytest.mark.asyncio
async def test_mock_replays_script_in_order():
    responses = [LLMResponse(text="first"), LLMResponse(text="second")]
    provider = MockProvider(responses)
    request = LLMRequest(messages=(Message.user("hi"),), system_prompt="sys")

    first = await provider.generate(request)
    second = await provider.generate(request)

    assert first.text == "first"
    assert second.text == "second"
    assert provider.remaining == 0
    assert len(provider.requests) == 2


@pytest.mark.asyncio
async def test_mock_records_requests_for_assertion():
    provider = MockProvider([LLMResponse(text="ok")])
    messages = (Message.user("hi"),)
    await provider.generate(LLMRequest(messages=messages, system_prompt="sys"))

    recorded = provider.requests[0]
    assert recorded.messages == messages
    assert recorded.system_prompt == "sys"


@pytest.mark.asyncio
async def test_mock_raises_when_script_exhausted():
    provider = MockProvider([LLMResponse(text="only one")])
    request = LLMRequest(messages=(Message.user("hi"),), system_prompt="sys")
    await provider.generate(request)
    with pytest.raises(MockProviderExhausted):
        await provider.generate(request)


def test_mock_supports_tool_use_responses():
    use = ToolUse(id="call_1", name="grep", input={"pattern": "TODO"})
    response = LLMResponse(text="let me search", tool_uses=(use,))
    assert response.wants_tool_use

    provider = MockProvider([response])
    assert provider.remaining == 1


def test_mock_reset_restores_cursor():
    provider = MockProvider([LLMResponse(text="x")])
    request = LLMRequest(messages=(Message.user("hi"),), system_prompt="sys")

    async def _consume():
        await provider.generate(request)

    import asyncio

    asyncio.run(_consume())
    provider.reset()
    assert provider.cursor == 0
    assert provider.remaining == 1
    assert provider.requests == []
