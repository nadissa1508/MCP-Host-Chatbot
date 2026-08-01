"""MCPClient: drives one server through the MCP lifecycle over a Transport.

Owns request/response correlation (by JSON-RPC id) and exposes the handful
of MCP operations a host needs: initialize, tools/list, tools/call, ping.
Frame logging is injected via `on_frame` so this module stays independent of
any particular logging/storage implementation.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from src.mcp.methods import (
    CLIENT_CAPABILITIES,
    CLIENT_NAME,
    CLIENT_VERSION,
    METHOD_INITIALIZE,
    METHOD_INITIALIZED,
    METHOD_PING,
    METHOD_TOOLS_CALL,
    METHOD_TOOLS_LIST,
    PROTOCOL_VERSION,
)
from src.mcp.models import InitializeResult, Tool, ToolResult
from src.mcp.transports.base import Transport
from src.protocol.errors import JsonRpcError
from src.protocol.jsonrpc import IdGenerator, JsonRpcNotification, JsonRpcRequest

FrameHook = Callable[[str, str, dict[str, Any]], None]
"""Called as hook(direction, server_name, message) for every frame sent or received.

direction is "send" or "recv".
"""

DEFAULT_TIMEOUT_SECONDS = 30.0


class MCPClient:
    def __init__(
        self,
        name: str,
        transport: Transport,
        on_frame: FrameHook | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.name = name
        self.transport = transport
        self.tools: list[Tool] = []
        self.server_info: InitializeResult | None = None

        self._on_frame = on_frame
        self._timeout = timeout
        self._ids = IdGenerator()
        self._pending: dict[int | str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Connect the transport, run the MCP handshake and cache the tool list."""
        await self.transport.connect()
        self._reader_task = asyncio.create_task(self._read_loop())

        init_result = await self._request(
            METHOD_INITIALIZE,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": CLIENT_CAPABILITIES,
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
        )
        self.server_info = InitializeResult.from_dict(init_result)
        await self._notify(METHOD_INITIALIZED, {})

        list_result = await self._request(METHOD_TOOLS_LIST, {})
        self.tools = [Tool.from_dict(t) for t in list_result.get("tools", [])]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        result = await self._request(METHOD_TOOLS_CALL, {"name": name, "arguments": arguments})
        return ToolResult.from_dict(result)

    async def ping(self) -> None:
        await self._request(METHOD_PING, {})

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        await self.transport.close()

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._ids.next()
        request = JsonRpcRequest(method=method, id=request_id, params=params)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        await self._send(request.to_dict())
        try:
            return await asyncio.wait_for(future, timeout=self._timeout)
        finally:
            self._pending.pop(request_id, None)

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        notification = JsonRpcNotification(method=method, params=params)
        await self._send(notification.to_dict())

    async def _send(self, message: dict[str, Any]) -> None:
        if self._on_frame:
            self._on_frame("send", self.name, message)
        await self.transport.send(message)

    async def _read_loop(self) -> None:
        while True:
            message = await self.transport.receive()
            if message is None:
                self._fail_all_pending(ConnectionError(f"server '{self.name}' closed the connection"))
                return

            if self._on_frame:
                self._on_frame("recv", self.name, message)

            if "id" in message and ("result" in message or "error" in message):
                self._resolve_pending(message)
            # Server-initiated requests/notifications (e.g. logging messages)
            # are logged via on_frame above; this client does not act on them.

    def _resolve_pending(self, message: dict[str, Any]) -> None:
        request_id = message["id"]
        future = self._pending.get(request_id)
        if future is None or future.done():
            return
        if "error" in message:
            err = message["error"]
            future.set_exception(JsonRpcError(err["code"], err["message"], err.get("data")))
        else:
            future.set_result(message["result"])

    def _fail_all_pending(self, exc: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
