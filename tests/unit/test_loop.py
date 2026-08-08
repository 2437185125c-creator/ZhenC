"""Tests for the agent loop — the full model/tool iteration."""
from __future__ import annotations

from pathlib import Path

import pytest

from code_review_harness.harness.loop import AgentLoop, MaxTurnsExceeded
from code_review_harness.harness.messages import ToolUse
from code_review_harness.llm.base import LLMResponse
from code_review_harness.llm.mock_provider import MockProvider
from code_review_harness.tools import SimpleToolExecutor, default_tool_registry

SYSTEM = "You are a review agent."


def make_loop(provider, *, max_turns=8, cwd=None, **kwargs):
    registry = default_tool_registry()
    return AgentLoop(
        provider=provider,
        tool_registry=registry,
        executor=SimpleToolExecutor(registry, Path(cwd or Path.cwd())),
        system_prompt=SYSTEM,
        cwd=Path(cwd or Path.cwd()),
        max_turns=max_turns,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_loop_runs_full_tool_cycle(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    responses = [
        LLMResponse(text="let me read", tool_uses=(ToolUse(id="call_1", name="read_file", input={"path": "app.py"}),)),
        LLMResponse(text="here is the review."),
    ]
    provider = MockProvider(responses)
    registry = default_tool_registry()
    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        executor=SimpleToolExecutor(registry, tmp_path),
        system_prompt=SYSTEM,
        cwd=tmp_path,
    )

    result = await loop.run("review app.py")

    assert result.final_text == "here is the review."
    assert result.turns == 2
    # The second request must have received the tool result.
    second_request = provider.requests[1]
    assert second_request.messages[-1].is_tool_response
    assert "x = 1" in second_request.messages[-1].tool_results[0].output
    # The tool specs were exposed to the model.
    assert {s.name for s in second_request.tools} >= {"read_file", "grep", "git_diff", "git_status"}


@pytest.mark.asyncio
async def test_loop_stops_when_no_tools(tmp_path):
    provider = MockProvider([LLMResponse(text="all good")])
    loop = make_loop(provider)
    result = await loop.run("review")
    assert result.final_text == "all good"
    assert result.turns == 1
    assert len(result.messages) == 2


@pytest.mark.asyncio
async def test_loop_raises_on_max_turns(tmp_path):
    responses = [
        LLMResponse(text="loop", tool_uses=(ToolUse(id="c", name="read_file", input={"path": "x.py"}),))
        for _ in range(5)
    ]
    provider = MockProvider(responses)
    loop = make_loop(provider, max_turns=2)
    with pytest.raises(MaxTurnsExceeded):
        await loop.run("review")


@pytest.mark.asyncio
async def test_loop_handles_unknown_tool_and_feeds_error_back(tmp_path):
    responses = [
        LLMResponse(text="bad tool", tool_uses=(ToolUse(id="c", name="does_not_exist", input={}),)),
        LLMResponse(text="ok, I understand"),
    ]
    provider = MockProvider(responses)
    loop = make_loop(provider)
    result = await loop.run("review")
    assert result.final_text == "ok, I understand"
    tool_result = provider.requests[1].messages[-1].tool_results[0]
    assert tool_result.is_error
    assert "Unknown tool" in tool_result.output


@pytest.mark.asyncio
async def test_loop_emits_events(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    responses = [
        LLMResponse(text="read", tool_uses=(ToolUse(id="c", name="read_file", input={"path": "app.py"}),)),
        LLMResponse(text="done"),
    ]
    provider = MockProvider(responses)
    events: list[str] = []

    async def sink(name: str, payload: dict) -> None:
        events.append(name)

    loop = AgentLoop(
        provider=provider,
        tool_registry=default_tool_registry(),
        executor=SimpleToolExecutor(default_tool_registry(), tmp_path),
        system_prompt=SYSTEM,
        cwd=tmp_path,
        on_event=sink,
    )
    await loop.run("review")
    assert "assistant_message" in events
    assert "tool_execution_started" in events
    assert "tool_execution_completed" in events
    assert "stop" in events
