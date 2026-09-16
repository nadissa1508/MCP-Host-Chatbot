"""Streamable HTTP transport: carries JSON-RPC frames as one POST per message
to a single MCP endpoint, matching the shape MCPClient expects from every
transport (send/receive as two independent operations) even though HTTP is
naturally request/response paired.

Each `send()` performs the POST and immediately parses whatever comes back
(a plain JSON body or a `text/event-stream` body with one or more `data:`
events) into an internal queue; `receive()` just drains that queue. This
keeps MCPClient's read loop -- written for stdio's independent input/output
streams -- unchanged for HTTP.
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
from contextlib import suppress
from typing import Any

import httpx

from src.mcp.methods import PROTOCOL_VERSION
from src.mcp.transports.base import Transport
from src.protocol.errors import JsonRpcError

SESSION_HEADER = "Mcp-Session-Id"
PROTOCOL_VERSION_HEADER = "MCP-Protocol-Version"


def _build_ssl_context() -> ssl.SSLContext | bool:
    """Log the TLS session keys to SSLKEYLOGFILE when it's set, so a capture
    of this traffic can be decrypted in Wireshark (Wireshark analysis
    deliverable). No-op in every other run: httpx's own default TLS
    verification is used when the variable isn't set."""
    keylog_path = os.environ.get("SSLKEYLOGFILE")
    if not keylog_path:
        return True
    context = ssl.create_default_context()
    context.keylog_filename = keylog_path
    return context


class StreamableHttpTransport(Transport):
    def __init__(self, url: str, timeout: float = 30.0):
        self._url = url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._session_id: str | None = None
        self._inbox: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._closed = False

    async def connect(self) -> None:
        if self._client is not None and not self._closed:
            return
        self._closed = False
        self._session_id = None
        self._inbox = asyncio.Queue()
        self._client = httpx.AsyncClient(timeout=self._timeout, verify=_build_ssl_context())

    async def send(self, message: dict[str, Any]) -> None:
        if self._client is None:
            raise ConnectionError("Streamable HTTP transport is not connected")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers[SESSION_HEADER] = self._session_id
            headers[PROTOCOL_VERSION_HEADER] = PROTOCOL_VERSION

        try:
            response = await self._client.post(self._url, json=message, headers=headers)
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"MCP request to {self._url} timed out") from exc
        except httpx.RequestError as exc:
            raise ConnectionError(f"MCP request to {self._url} failed: {exc}") from exc

        if response.status_code == 404 and self._session_id:
            # The server no longer recognizes our session (e.g. it restarted).
            self._session_id = None
            raise ConnectionError("MCP session expired; reconnect required")
        if response.status_code >= 400:
            raise JsonRpcError.internal_error(
                f"HTTP {response.status_code} from {self._url}: {response.text}"
            )

        new_session = response.headers.get(SESSION_HEADER)
        if new_session:
            self._session_id = new_session

        # A notification never gets a body back (202 Accepted, empty).
        if response.status_code == 202 or not response.content:
            return

        try:
            decoded_messages = self._parse_body(response)
        except (json.JSONDecodeError, ValueError) as exc:
            raise JsonRpcError.parse_error(f"Invalid HTTP response body: {exc}") from exc

        for decoded in decoded_messages:
            self._inbox.put_nowait(decoded)

    def _parse_body(self, response: httpx.Response) -> list[dict[str, Any]]:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return self._parse_sse(response.text)
        message = response.json()
        if not isinstance(message, dict):
            raise ValueError("the response JSON is not an object")
        return [message]

    @staticmethod
    def _parse_sse(body: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        data_lines: list[str] = []

        def append_event() -> None:
            if not data_lines:
                return
            decoded = json.loads("\n".join(data_lines))
            if not isinstance(decoded, dict):
                raise ValueError("an SSE data event is not a JSON object")
            messages.append(decoded)
            data_lines.clear()

        # splitlines() handles both LF and CRLF framing. A blank line ends
        # one SSE event; comments and fields other than data are ignored.
        for line in body.splitlines():
            if not line:
                append_event()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())
        append_event()
        return messages

    async def receive(self) -> dict[str, Any] | None:
        if self._closed and self._inbox.empty():
            return None
        return await self._inbox.get()

    async def close(self) -> None:
        if self._client is not None and self._session_id:
            with suppress(httpx.HTTPError):
                await self._client.delete(
                    self._url,
                    headers={SESSION_HEADER: self._session_id},
                )
        self._closed = True
        self._inbox.put_nowait(None)
        if self._client is not None:
            await self._client.aclose()
        self._client = None
        self._session_id = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and not self._closed
