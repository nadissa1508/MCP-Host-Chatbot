"""The MCP host: owns one MCPClient per configured server and wires the
tool registry, LLM provider and agent loop together for a chat session.
"""

from __future__ import annotations

import sys

from src.host.agent_loop import AgentLoop
from src.host.config import AppConfig, ServerConfig
from src.host.conversation import Conversation
from src.host.registry import ToolRegistry
from src.llm.anthropic_api import AnthropicClient
from src.mcp.client import MCPClient
from src.mcp.transports.base import Transport
from src.mcp.transports.stdio import StdioTransport
from src.observability.mcp_log import MCPLogger

SYSTEM_PROMPT = (
    "You are a helpful terminal assistant with access to external tools "
    "through the Model Context Protocol. Use the available tools whenever "
    "they let you give a more accurate or up-to-date answer, and explain "
    "what you did in plain language. Always reply in the same language the "
    "user's message is written in."
)


def _build_transport(config: ServerConfig) -> Transport:
    if config.transport == "stdio":
        if not config.command:
            raise ValueError(f"server '{config.name}' is stdio but has no command")
        return StdioTransport(command=config.command, args=config.args or [])
    raise NotImplementedError(
        f"server '{config.name}' uses transport '{config.transport}', "
        "which is not wired up in this build"
    )


class Host:
    def __init__(self, config: AppConfig):
        self.config = config
        self.logger = MCPLogger()
        self.registry = ToolRegistry()
        self.clients: dict[str, MCPClient] = {}
        self.llm = AnthropicClient(config.anthropic_api_key, config.anthropic_model)
        self.conversation = Conversation(SYSTEM_PROMPT)
        self.agent_loop = AgentLoop(self.llm, self.registry, self.conversation, self.logger)
        self._connect_errors: dict[str, str] = {}

    async def start(self) -> None:
        for server_config in self.config.servers:
            if not server_config.enabled:
                continue
            await self._connect_server(server_config)

    async def _connect_server(self, server_config: ServerConfig) -> None:
        try:
            transport = _build_transport(server_config)
        except NotImplementedError as exc:
            self._connect_errors[server_config.name] = str(exc)
            return

        client = MCPClient(server_config.name, transport, on_frame=self.logger.log_frame)
        try:
            await client.start()
        except Exception as exc:  # noqa: BLE001 - surface any startup failure to the user
            self._connect_errors[server_config.name] = f"{type(exc).__name__}: {exc}"
            print(f"[host] no se pudo iniciar el servidor '{server_config.name}': {exc}", file=sys.stderr)
            return

        self.clients[server_config.name] = client
        self.registry.register_client(client)

    def connection_errors(self) -> dict[str, str]:
        return dict(self._connect_errors)

    async def shutdown(self) -> None:
        for client in self.clients.values():
            await client.close()
        await self.llm.close()
        self.logger.close()
