"""Drives one user turn through the LLM, executing any tool calls it makes.

The loop is: send the conversation + tool catalog to the LLM; if it stops
because it wants to use a tool, run each tool call through the registry,
feed the results back as a user turn, and ask the LLM again. Repeat until it
stops for any other reason (or a safety cap on iterations is hit).
"""

from __future__ import annotations

from src.host.conversation import Conversation
from src.host.registry import ToolRegistry
from src.llm.base import LLMProvider
from src.observability.mcp_log import MCPLogger

MAX_TOOL_ITERATIONS = 10


class AgentLoop:
    def __init__(
        self,
        llm: LLMProvider,
        registry: ToolRegistry,
        conversation: Conversation,
        logger: MCPLogger | None = None,
    ):
        self._llm = llm
        self._registry = registry
        self._conversation = conversation
        self._logger = logger

    async def run_turn(self, user_text: str) -> str:
        self._conversation.add_user_text(user_text)

        for _ in range(MAX_TOOL_ITERATIONS):
            response = await self._llm.send(
                messages=self._conversation.history(),
                tools=self._registry.to_anthropic_tools(),
                system=self._conversation.system_prompt,
            )
            self._conversation.add_assistant_blocks(response.content)

            tool_uses = response.tool_uses()
            if response.stop_reason != "tool_use" or not tool_uses:
                return response.text()

            tool_results = []
            for call in tool_uses:
                result = await self._registry.call(call["name"], call.get("input", {}))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                )
            self._conversation.add_tool_results(tool_results)

        return "Stopped after too many tool-call iterations without a final answer."
