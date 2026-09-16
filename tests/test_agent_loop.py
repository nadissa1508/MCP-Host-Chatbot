from typing import Any

import pytest

from src.host.agent_loop import AgentLoop
from src.host.conversation import Conversation
from src.llm.base import LLMProvider, LLMResponse
from src.mcp.models import ToolResult


class ScriptedLLM(LLMProvider):
    def __init__(self, responses: list[LLMResponse]):
        self.responses = iter(responses)
        self.calls: list[list[dict[str, Any]]] = []

    async def send(self, messages, tools, system):
        self.calls.append(list(messages))
        return next(self.responses)

    async def close(self) -> None:
        return None


class RecordingRegistry:
    def __init__(self):
        self.calls = []

    def to_anthropic_tools(self):
        return [{"name": "pharmacy__check_stock", "input_schema": {"type": "object"}}]

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        return ToolResult.text_result('{"quantity": 12}')


@pytest.mark.asyncio
async def test_agent_loop_keeps_context_across_user_turns():
    llm = ScriptedLLM(
        [
            LLMResponse(content=[{"type": "text", "text": "Alan Turing."}], stop_reason="end_turn"),
            LLMResponse(content=[{"type": "text", "text": "He was born in 1912."}], stop_reason="end_turn"),
        ]
    )
    conversation = Conversation("system")
    loop = AgentLoop(llm, RecordingRegistry(), conversation)

    await loop.run_turn("Who was Alan Turing?")
    answer = await loop.run_turn("When was he born?")

    assert answer == "He was born in 1912."
    second_call = llm.calls[1]
    assert [message["role"] for message in second_call] == ["user", "assistant", "user"]
    assert second_call[1]["content"][0]["text"] == "Alan Turing."


@pytest.mark.asyncio
async def test_agent_loop_executes_tool_and_returns_final_answer():
    llm = ScriptedLLM(
        [
            LLMResponse(
                content=[
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "pharmacy__check_stock",
                        "input": {"sku": "LORA10"},
                    }
                ],
                stop_reason="tool_use",
            ),
            LLMResponse(
                content=[{"type": "text", "text": "There are 12 units available."}],
                stop_reason="end_turn",
            ),
        ]
    )
    registry = RecordingRegistry()
    loop = AgentLoop(llm, registry, Conversation("system"))

    answer = await loop.run_turn("Is loratadine in stock?")

    assert answer == "There are 12 units available."
    assert registry.calls == [("pharmacy__check_stock", {"sku": "LORA10"})]
    tool_result_message = llm.calls[1][-1]
    assert tool_result_message["content"][0]["tool_use_id"] == "tool-1"
