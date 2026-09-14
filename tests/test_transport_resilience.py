import asyncio
import json
from types import SimpleNamespace

import pytest

from src.host.config import load_server_configs
from src.host.registry import ToolRegistry
from src.mcp.client import MCPClient
from src.mcp.models import Tool
from src.mcp.transports.base import Transport
from src.mcp.transports.stdio import StdioTransport


class SendFailureTransport(Transport):
    def __init__(self):
        self.connected = False
        self.closed = False

    async def connect(self) -> None:
        self.connected = True

    async def send(self, message: dict) -> None:
        raise ConnectionError("simulated send failure")

    async def receive(self) -> dict | None:
        await asyncio.Event().wait()

    async def close(self) -> None:
        self.connected = False
        self.closed = True

    @property
    def is_connected(self) -> bool:
        return self.connected


@pytest.mark.asyncio
async def test_client_start_failure_closes_transport_and_clears_pending_requests():
    transport = SendFailureTransport()
    client = MCPClient("broken", transport)

    with pytest.raises(ConnectionError, match="simulated send failure"):
        await client.start()

    assert transport.closed is True
    assert client._pending == {}


@pytest.mark.asyncio
async def test_stdio_receive_skips_malformed_line_instead_of_reporting_eof():
    reader = asyncio.StreamReader()
    reader.feed_data(b"not-json\n")
    reader.feed_data(b'{"jsonrpc":"2.0","id":1,"result":{}}\n')
    reader.feed_eof()

    transport = StdioTransport("unused")
    transport._process = SimpleNamespace(stdout=reader)

    message = await transport.receive()
    assert message == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_server_url_can_be_resolved_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("PHARMACY_REMOTE_URL", "https://example.test/mcp")
    path = tmp_path / "servers.json"
    path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "name": "remote",
                        "transport": "http",
                        "enabled": True,
                        "url": "${PHARMACY_REMOTE_URL}",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    [server] = load_server_configs(path)
    assert server.url == "https://example.test/mcp"


@pytest.mark.asyncio
async def test_registry_turns_transport_failure_into_tool_error():
    class FailingClient:
        name = "remote"
        tools = [Tool("search", "Search", {"type": "object"})]

        async def call_tool(self, name, arguments):
            raise TimeoutError("simulated timeout")

    registry = ToolRegistry()
    registry.register_client(FailingClient())

    result = await registry.call("remote__search", {})

    assert result.is_error is True
    assert "simulated timeout" in result.text()
