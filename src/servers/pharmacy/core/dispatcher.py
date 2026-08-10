"""Transport-agnostic MCP request handling for the pharmacy server.

handle() takes one decoded JSON-RPC message and returns the dict to send
back (or None for notifications, which get no reply). Both stdio_server.py
and http_server.py are thin adapters around this single class.
"""

from __future__ import annotations

from typing import Any

from src.mcp.methods import (
    METHOD_INITIALIZE,
    METHOD_INITIALIZED,
    METHOD_PING,
    METHOD_TOOLS_CALL,
    METHOD_TOOLS_LIST,
    PROTOCOL_VERSION,
)
from src.protocol.errors import JsonRpcError
from src.protocol.jsonrpc import (
    JsonRpcErrorResponse,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    parse_message,
)
from src.servers.pharmacy.core.tools import TOOLS

SERVER_NAME = "pharmacy-mcp"
SERVER_VERSION = "0.1.0"


class Dispatcher:
    def __init__(self) -> None:
        self._tools = {tool.name: tool for tool in TOOLS}

    def handle(self, raw_message: dict[str, Any]) -> dict[str, Any] | None:
        try:
            message = parse_message(raw_message)
        except JsonRpcError as exc:
            return JsonRpcErrorResponse(id=raw_message.get("id"), error=exc).to_dict()

        if isinstance(message, JsonRpcNotification):
            self._handle_notification(message)
            return None

        if isinstance(message, JsonRpcRequest):
            try:
                result = self._handle_request(message)
                return JsonRpcResponse(id=message.id, result=result).to_dict()
            except JsonRpcError as exc:
                return JsonRpcErrorResponse(id=message.id, error=exc).to_dict()

        # Responses/errors addressed to us are not expected; ignore them.
        return None

    def _handle_notification(self, notification: JsonRpcNotification) -> None:
        # notifications/initialized carries no server-side action for this
        # server: there is no per-session state to activate.
        return None

    def _handle_request(self, request: JsonRpcRequest) -> dict[str, Any]:
        if request.method == METHOD_INITIALIZE:
            return self._initialize()
        if request.method == METHOD_TOOLS_LIST:
            return {"tools": [tool.to_schema() for tool in self._tools.values()]}
        if request.method == METHOD_TOOLS_CALL:
            return self._tools_call(request.params or {})
        if request.method == METHOD_PING:
            return {}
        raise JsonRpcError.method_not_found(request.method)

    def _initialize(self) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }

    def _tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        tool = self._tools.get(name)
        if tool is None:
            raise JsonRpcError.invalid_params(f"Unknown tool: {name}")
        return tool.call(arguments).to_dict()
