"""Typed views over the JSON payloads exchanged during MCP tool use."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Tool:
    """One tool advertised by a server's `tools/list` response."""

    name: str
    description: str
    input_schema: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Tool":
        return cls(
            name=raw["name"],
            description=raw.get("description", ""),
            input_schema=raw.get("inputSchema", {"type": "object", "properties": {}}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class ToolResult:
    """The outcome of a `tools/call`."""

    content: list[dict[str, Any]]
    is_error: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ToolResult":
        return cls(content=raw.get("content", []), is_error=bool(raw.get("isError", False)))

    def to_dict(self) -> dict[str, Any]:
        return {"content": self.content, "isError": self.is_error}

    def text(self) -> str:
        """Concatenate every text block in the result, for quick display/logging."""
        return "\n".join(
            block.get("text", "") for block in self.content if block.get("type") == "text"
        )

    @classmethod
    def text_result(cls, text: str, is_error: bool = False) -> "ToolResult":
        return cls(content=[{"type": "text", "text": text}], is_error=is_error)


@dataclass
class ServerInfo:
    """The `serverInfo` block a server returns from `initialize`."""

    name: str
    version: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ServerInfo":
        return cls(name=raw.get("name", "unknown"), version=raw.get("version", "0.0.0"))


@dataclass
class InitializeResult:
    """The full result of the `initialize` handshake."""

    protocol_version: str
    capabilities: dict[str, Any]
    server_info: ServerInfo

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "InitializeResult":
        return cls(
            protocol_version=raw.get("protocolVersion", ""),
            capabilities=raw.get("capabilities", {}),
            server_info=ServerInfo.from_dict(raw.get("serverInfo", {})),
        )
