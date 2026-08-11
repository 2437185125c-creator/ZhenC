"""OpenAI-compatible chat completions provider.

Converts the harness's provider-agnostic messages/tools to the OpenAI chat
completions wire format and streams back a structured :class:`LLMResponse`.
Works with OpenAI and any OpenAI-compatible endpoint (Azure, local gateways,
domestic relays) by pointing ``base_url`` at it.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from code_review_harness.harness.messages import Message, ToolUse
from code_review_harness.llm.base import LLMProvider, LLMRequest, LLMResponse
import os
from dotenv import load_dotenv


load_dotenv()
API_KEY= os.getenv("API_KEY")


log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120.0


def messages_to_openai(messages: tuple[Message, ...]) -> list[dict[str, Any]]:
    """Convert harness messages to the OpenAI chat format."""
    wire: list[dict[str, Any]] = []
    for message in messages:
        if message.tool_results:
            # Tool responses form their own user-role messages.
            wire.extend(
                {
                    "role": "tool",
                    "tool_call_id": result.id,
                    "content": result.output,
                }
                for result in message.tool_results
            )
            continue
        if message.role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": message.text}
            if message.tool_uses:
                entry["tool_calls"] = [
                    {
                        "id": use.id,
                        "type": "function",
                        "function": {
                            "name": use.name,
                            "arguments": json.dumps(use.input, default=str),
                        },
                    }
                    for use in message.tool_uses
                ]
            wire.append(entry)
        else:
            wire.append({"role": message.role, "content": message.text})
    return wire


def tools_to_openai(specs) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.input_schema,
            },
        }
        for spec in specs
    ]


class OpenAICompatProvider(LLMProvider):
    """Async LLM provider against any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        *,
        api_key: str = API_KEY,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-flash",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def generate(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": messages_to_openai(request.messages),
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            payload["tools"] = tools_to_openai(request.tools)

        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"LLM API error {response.status_code}: {response.text[:500]}"
            )

        data = response.json()
        choice = data["choices"][0]
        message = choice.get("message", {})

        text = message.get("content") or ""
        tool_uses: tuple[ToolUse, ...] = ()
        raw_calls = message.get("tool_calls") or []
        for call in raw_calls:
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_uses += (
                ToolUse(
                    id=call["id"],
                    name=call["function"]["name"],
                    input=arguments,
                ),
            )
        return LLMResponse(text=text, tool_uses=tool_uses)
