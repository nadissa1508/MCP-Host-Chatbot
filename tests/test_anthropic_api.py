import json

import httpx
import pytest

from src.llm.anthropic_api import API_VERSION, AnthropicClient


async def _client_with_handler(handler) -> AnthropicClient:
    client = AnthropicClient("test-key", "test-model")
    await client._http.aclose()
    client._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={
            "x-api-key": "test-key",
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
    )
    return client


@pytest.mark.asyncio
async def test_anthropic_client_sends_history_tools_and_parses_response():
    def successful(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.headers["x-api-key"] == "test-key"
        assert request.headers["anthropic-version"] == API_VERSION
        assert body["model"] == "test-model"
        assert body["messages"][0]["content"][0]["text"] == "Hello"
        assert body["tools"][0]["name"] == "pharmacy__check_stock"
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Hi"}],
                "stop_reason": "end_turn",
            },
        )

    client = await _client_with_handler(successful)
    try:
        response = await client.send(
            messages=[{"role": "user", "content": [{"type": "text", "text": "Hello"}]}],
            tools=[{"name": "pharmacy__check_stock", "input_schema": {"type": "object"}}],
            system="Be helpful",
        )
    finally:
        await client.close()

    assert response.text() == "Hi"
    assert response.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_anthropic_client_surfaces_api_error_details():
    def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid API key")

    client = await _client_with_handler(rejected)
    try:
        with pytest.raises(RuntimeError, match="Anthropic API error 401"):
            await client.send(messages=[], tools=[], system="Be helpful")
    finally:
        await client.close()
