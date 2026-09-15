import asyncio

import httpx
import pytest
import uvicorn

from src.mcp.client import MCPClient
from src.mcp.transports.streamable_http import (
    PROTOCOL_VERSION_HEADER,
    SESSION_HEADER,
    StreamableHttpTransport,
)
from src.protocol.errors import JsonRpcError
from src.servers.pharmacy.http_server import active_sessions, app


@pytest.fixture
async def server_url():
    """Runs the real pharmacy HTTP server on an OS-assigned loopback port,
    so the transport is exercised over an actual socket instead of an
    in-process ASGI call."""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)

    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        await task


@pytest.mark.asyncio
async def test_streamable_http_client_full_lifecycle(server_url):
    """End-to-end check of the client-side Streamable HTTP transport against
    the real server over a real socket: initialize, tools/list, tools/call,
    and that the Mcp-Session-Id captured from initialize is reused."""
    transport = StreamableHttpTransport(server_url)
    client = MCPClient("pharmacy-remote", transport)

    session_id = None
    try:
        await client.start()

        assert client.server_info is not None
        assert client.server_info.server_info.name == "pharmacy-mcp"
        assert transport._session_id is not None
        session_id = transport._session_id
        tool_names = {t.name for t in client.tools}
        assert "check_stock" in tool_names

        result = await client.call_tool("search_medications", {"therapeutic_class": "antihistamine"})
        assert result.is_error is False
        assert "LORA10" in result.text()

        error_result = await client.call_tool("get_medication_details", {"sku": "DOES-NOT-EXIST"})
        assert error_result.is_error is True
    finally:
        await client.close()

    assert session_id not in active_sessions


def test_sse_parser_supports_crlf_and_multiple_events():
    body = (
        'event: message\r\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\r\n\r\n'
        'event: message\r\ndata: {"jsonrpc":"2.0","id":2,"result":{}}\r\n\r\n'
    )
    messages = StreamableHttpTransport._parse_sse(body)
    assert [message["id"] for message in messages] == [1, 2]


async def _transport_with_handler(handler) -> StreamableHttpTransport:
    transport = StreamableHttpTransport("https://example.test/mcp")
    await transport.connect()
    await transport._client.aclose()
    transport._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return transport


@pytest.mark.asyncio
async def test_http_transport_turns_timeout_into_timeout_error():
    def timeout(request):
        raise httpx.ReadTimeout("simulated timeout", request=request)

    transport = await _transport_with_handler(timeout)
    try:
        with pytest.raises(TimeoutError, match="timed out"):
            await transport.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_http_transport_surfaces_http_status_details():
    def unavailable(request):
        return httpx.Response(503, text="temporarily unavailable")

    transport = await _transport_with_handler(unavailable)
    try:
        with pytest.raises(JsonRpcError, match="HTTP 503"):
            await transport.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_http_transport_rejects_invalid_response_body():
    def invalid_body(request):
        return httpx.Response(200, text="not-json", headers={"content-type": "application/json"})

    transport = await _transport_with_handler(invalid_body)
    try:
        with pytest.raises(JsonRpcError, match="Invalid HTTP response body"):
            await transport.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_http_transport_clears_expired_session():
    def expired(request):
        return httpx.Response(404, text="unknown session")

    transport = await _transport_with_handler(expired)
    transport._session_id = "expired"
    try:
        with pytest.raises(ConnectionError, match="session expired"):
            await transport.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert transport._session_id is None
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_http_transport_sends_session_and_protocol_version_headers():
    observed_headers = None

    def successful(request):
        nonlocal observed_headers
        observed_headers = request.headers
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 2, "result": {}},
        )

    transport = await _transport_with_handler(successful)
    transport._session_id = "active-session"
    try:
        await transport.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert observed_headers[SESSION_HEADER] == "active-session"
        assert observed_headers[PROTOCOL_VERSION_HEADER] == "2025-06-18"
    finally:
        await transport.close()
