"""Transport abstraction: anything that can carry JSON-RPC frames to a server.

MCPClient is written against this interface only, so stdio (subprocess pipes)
and Streamable HTTP (POST + SSE) are interchangeable from the client's point
of view -- swapping one config entry is enough to move a server from local to
remote.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Transport(ABC):
    """Sends and receives one JSON-RPC message (as a plain dict) at a time."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish the underlying connection (spawn a process, open a session, ...)."""

    @abstractmethod
    async def send(self, message: dict[str, Any]) -> None:
        """Write one JSON-RPC message to the server."""

    @abstractmethod
    async def receive(self) -> dict[str, Any] | None:
        """Read the next JSON-RPC message from the server, or None on EOF."""

    @abstractmethod
    async def close(self) -> None:
        """Tear down the connection."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        ...
