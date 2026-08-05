"""Records every JSON-RPC frame exchanged with any MCP server.

Frames are appended to a JSONL file (one JSON object per line, easy to grep
or replay) and kept in a bounded in-memory ring buffer so the terminal UI
can show recent traffic without re-reading the file.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_LOG_DIR = Path("logs")
DEFAULT_RING_SIZE = 500


@dataclass
class LogEntry:
    timestamp: float
    direction: str  # "send" or "recv"
    server: str
    message: dict[str, Any]

    def kind(self) -> str:
        """Classify the frame per JSON-RPC shape: request, response, error or notification."""
        if "method" in self.message:
            return "request" if "id" in self.message else "notification"
        if "error" in self.message:
            return "error"
        return "response"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "direction": self.direction,
            "server": self.server,
            "kind": self.kind(),
            "message": self.message,
        }


@dataclass
class MCPLogger:
    log_dir: Path = field(default_factory=lambda: DEFAULT_LOG_DIR)
    ring_size: int = DEFAULT_RING_SIZE

    def __post_init__(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._ring: deque[LogEntry] = deque(maxlen=self.ring_size)
        self._path = self.log_dir / f"mcp-{int(time.time())}.jsonl"
        self._file = self._path.open("a", encoding="utf-8")

    def log_frame(self, direction: str, server: str, message: dict[str, Any]) -> None:
        entry = LogEntry(timestamp=time.time(), direction=direction, server=server, message=message)
        self._ring.append(entry)
        self._file.write(json.dumps(entry.to_dict()) + "\n")
        self._file.flush()

    def recent(self, count: int = 20) -> list[LogEntry]:
        return list(self._ring)[-count:]

    def close(self) -> None:
        self._file.close()

    @property
    def path(self) -> Path:
        return self._path
