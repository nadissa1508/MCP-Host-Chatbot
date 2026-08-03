"""Raw HTTP client for the Anthropic Messages API.

Deliberately avoids the `anthropic` SDK so that the request/response shape
stays visible: this module builds the JSON body, sends it with a plain
`httpx.AsyncClient` and parses the reply by hand.
"""

from __future__ import annotations

from typing import Any

import httpx

from src.llm.base import LLMProvider, LLMResponse
from src.mcp.models import Tool

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096


def tool_to_anthropic_schema(tool: Tool) -> dict[str, Any]:
    """Translate one MCP Tool into the `tools` entry shape Anthropic expects."""
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


class AnthropicClient(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: float = 60.0,
    ):
        self._model = model
        self._max_tokens = max_tokens
        self._http = httpx.AsyncClient(
            headers={
                "x-api-key": api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            timeout=timeout,
        )

    async def send(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools

        response = await self._http.post(API_URL, json=body)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Anthropic API error {response.status_code}: {response.text}"
            )

        data = response.json()
        return LLMResponse(
            content=data.get("content", []),
            stop_reason=data.get("stop_reason", ""),
            raw=data,
        )

    async def close(self) -> None:
        await self._http.aclose()
