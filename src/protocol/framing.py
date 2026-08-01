"""Newline-delimited JSON framing, used to send JSON-RPC messages over stdio.

Each frame is one JSON object serialized on a single line and terminated by
"\n". This is the framing scheme MCP's stdio transport uses (as opposed to
Content-Length-prefixed framing used by LSP-style protocols).
"""

from __future__ import annotations

import json
from typing import Any

from src.protocol.errors import JsonRpcError


def encode_frame(message: dict[str, Any]) -> bytes:
    """Serialize a message dict into one newline-terminated JSON line."""
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


def decode_frame(line: bytes | str) -> dict[str, Any]:
    """Parse one line of text back into a message dict.

    Raises JsonRpcError(PARSE_ERROR) on malformed JSON, per the JSON-RPC spec.
    """
    text = line.decode("utf-8") if isinstance(line, bytes) else line
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonRpcError.parse_error(str(exc)) from exc
