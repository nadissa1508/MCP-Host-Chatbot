"""MCP method names and the lifecycle constants used during a handshake."""

PROTOCOL_VERSION = "2025-06-18"

METHOD_INITIALIZE = "initialize"
METHOD_INITIALIZED = "notifications/initialized"
METHOD_PING = "ping"
METHOD_TOOLS_LIST = "tools/list"
METHOD_TOOLS_CALL = "tools/call"

CLIENT_NAME = "mcp-host-chatbot"
CLIENT_VERSION = "0.1.0"

CLIENT_CAPABILITIES: dict = {}
