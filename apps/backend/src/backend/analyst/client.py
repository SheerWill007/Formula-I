"""Chat client with native tool calling (OpenRouter, OpenAI-compatible).

Kept separate from backend.agent.llm, which only does plain completions. The
loop depends on the small ChatClient protocol so tests can script replies.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from backend.config import settings
from backend.net import safe_urlopen

# USD per 1M tokens (input, output). Used only when the provider reports no cost.
_PRICES = {"openai/gpt-4o-mini": (0.15, 0.60)}


# Per reply. Generous for a script or an answer, small enough that a runaway
# generation (seen: a 4-minute empty final answer) cannot burn time and money.
MAX_OUTPUT_TOKENS = 2500


class AnalystLLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string as the model wrote it


@dataclass(frozen=True)
class Reply:
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_message: dict = field(default_factory=dict)


class ChatClient(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None) -> Reply: ...


class OpenRouterClient:
    def __init__(self, model: str | None = None, timeout_s: int = 60) -> None:
        self.model = model or settings.analyst_model
        self.timeout_s = timeout_s

    def chat(self, messages: list[dict], tools: list[dict] | None) -> Reply:
        if not settings.openrouter_api_key:
            raise AnalystLLMError("OPENROUTER_API_KEY is not configured")
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "usage": {"include": True},
        }
        if tools:
            payload["tools"] = tools
        request = urllib.request.Request(
            f"{settings.openrouter_base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with safe_urlopen(request, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise AnalystLLMError(f"LLM request failed: {exc}") from exc

        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise AnalystLLMError(
                f"unexpected LLM response: {str(body)[:200]}"
            ) from exc

        usage = body.get("usage") or {}
        prompt, completion = (
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )
        cost = usage.get("cost")
        if cost is None:
            price_in, price_out = _PRICES.get(self.model, (0.0, 0.0))
            cost = (prompt * price_in + completion * price_out) / 1_000_000
        calls = tuple(
            ToolCall(
                c["id"], c["function"]["name"], c["function"].get("arguments") or "{}"
            )
            for c in (message.get("tool_calls") or [])
        )
        return Reply(
            content=message.get("content") or "",
            tool_calls=calls,
            cost_usd=float(cost),
            prompt_tokens=prompt,
            completion_tokens=completion,
            raw_message=message,
        )
