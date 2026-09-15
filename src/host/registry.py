"""Merges the tool catalogs of every connected MCP server into one namespace.

Tool names are namespaced as "<server>__<tool>" so two servers can expose a
tool with the same short name without colliding, and so a call can be routed
back to the right MCPClient just by parsing the name.
"""

from __future__ import annotations

from typing import Any

from src.llm.anthropic_api import tool_to_anthropic_schema
from src.mcp.client import MCPClient
from src.mcp.models import ToolResult
from src.protocol.errors import JsonRpcError

NAMESPACE_SEPARATOR = "__"


class ToolRegistry:
    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._routes: dict[str, tuple[str, str]] = {}  # namespaced -> (server, original)

    def register_client(self, client: MCPClient) -> None:
        self._clients[client.name] = client
        for tool in client.tools:
            namespaced = f"{client.name}{NAMESPACE_SEPARATOR}{tool.name}"
            self._routes[namespaced] = (client.name, tool.name)

    def to_anthropic_tools(self) -> list[dict[str, Any]]:
        tools = []
        for client in self._clients.values():
            for tool in client.tools:
                schema = tool_to_anthropic_schema(tool)
                schema["name"] = f"{client.name}{NAMESPACE_SEPARATOR}{tool.name}"
                tools.append(schema)
        return tools

    async def call(self, namespaced_name: str, arguments: dict[str, Any]) -> ToolResult:
        route = self._routes.get(namespaced_name)
        if route is None:
            return ToolResult.text_result(f"Unknown tool: {namespaced_name}", is_error=True)
        server_name, original_name = route
        client = self._clients[server_name]
        try:
            return await client.call_tool(original_name, arguments)
        except (ConnectionError, TimeoutError, JsonRpcError) as exc:
            return ToolResult.text_result(
                f"The MCP server '{server_name}' could not complete the tool call: {exc}",
                is_error=True,
            )

    def server_names(self) -> list[str]:
        return list(self._clients.keys())

    def tool_count(self, server_name: str) -> int:
        return len(self._clients[server_name].tools)
