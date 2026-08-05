"""Human-readable formatting of logged MCP frames for the terminal `/log` view."""

from __future__ import annotations

import json
import time

from src.observability.mcp_log import LogEntry

DIRECTION_ARROWS = {"send": "->", "recv": "<-"}
KIND_LABELS = {
    "request": "REQUEST",
    "response": "RESPONSE",
    "error": "ERROR",
    "notification": "NOTIFY",
}


def format_entry(entry: LogEntry) -> str:
    ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
    arrow = DIRECTION_ARROWS.get(entry.direction, "?")
    label = KIND_LABELS.get(entry.kind(), entry.kind().upper())
    method = entry.message.get("method")
    summary = method if method else f"id={entry.message.get('id')}"
    body = json.dumps(entry.message, indent=2)
    return f"[{ts}] {arrow} {entry.server:<16} {label:<10} {summary}\n{body}"


def format_recent(entries: list[LogEntry]) -> str:
    return "\n\n".join(format_entry(e) for e in entries)
