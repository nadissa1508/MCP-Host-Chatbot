import sys

import pytest

from src.mcp.client import MCPClient
from src.mcp.transports.stdio import StdioTransport


@pytest.mark.asyncio
async def test_mcp_client_full_lifecycle_against_pharmacy_server():
    """End-to-end check of the hand-written protocol stack: spawns the real
    pharmacy stdio server as a subprocess and drives it through the full MCP
    lifecycle over actual stdin/stdout pipes."""
    transport = StdioTransport(command=sys.executable, args=["-m", "src.servers.pharmacy.stdio_server"])
    client = MCPClient("pharmacy", transport)

    try:
        await client.start()

        assert client.server_info is not None
        assert client.server_info.server_info.name == "pharmacy-mcp"
        tool_names = {t.name for t in client.tools}
        assert "assess_symptoms" in tool_names
        assert "check_stock" in tool_names

        result = await client.call_tool("search_medications", {"therapeutic_class": "antihistamine"})
        assert result.is_error is False
        assert "LORA10" in result.text()

        error_result = await client.call_tool("get_medication_details", {"sku": "DOES-NOT-EXIST"})
        assert error_result.is_error is True
    finally:
        await client.close()
