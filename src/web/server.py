"""Web entrypoint for the MCP host chatbot.

Wraps the same Host/AgentLoop used by src/main.py's terminal REPL behind a
small Starlette app: one WebSocket carries the chat, and every MCP tool
call made during a turn is pushed to the browser as it happens so the
frontend can show a tool badge and switch the chat's theme (blue/white for
filesystem + git, Meykos-inspired for the pharmacy server) depending on
which MCP server is actually doing the work - the host and the MCP
protocol layer underneath are unchanged.

Run with: python -m src.web.server (serves on http://0.0.0.0:8000)
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import FileResponse
from starlette.routing import Route, Mount, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from src.host.config import AppConfig
from src.host.host import Host

STATIC_DIR = Path(__file__).parent / "static"

host: Host | None = None
_frame_subscribers: list[asyncio.Queue] = []


def _server_mode(server_name: str) -> str:
    """Which UI theme a server's tool calls should drive."""
    return "pharmacy" if server_name.startswith("pharmacy") else "dev"


def _broadcast_frame(direction: str, server: str, message: dict) -> None:
    """Fan out every MCP frame to whichever turn is currently listening,
    in addition to the normal JSONL/ring-buffer logging Host already does."""
    if direction == "send" and message.get("method") == "tools/call":
        tool_name = message.get("params", {}).get("name", "?")
        event = {"type": "tool_call", "server": server, "tool": tool_name, "mode": _server_mode(server)}
        for queue in _frame_subscribers:
            queue.put_nowait(event)


@asynccontextmanager
async def lifespan(app: Starlette):
    global host
    config = AppConfig.load()
    host = Host(config)

    # Piggyback on the same on_frame hook the terminal /log command reads
    # from, without changing MCPLogger's own file/ring-buffer behavior.
    # Must be wrapped before start() connects any client, since each
    # MCPClient captures host.logger.log_frame at connect time.
    original_log_frame = host.logger.log_frame

    def log_frame(direction: str, server: str, message: dict) -> None:
        original_log_frame(direction, server, message)
        _broadcast_frame(direction, server, message)

    host.logger.log_frame = log_frame  # type: ignore[method-assign]

    await host.start()
    try:
        yield
    finally:
        await host.shutdown()


async def index(request):
    return FileResponse(STATIC_DIR / "index.html")


async def status(request):
    assert host is not None
    return _json_response(
        {
            "servers": [
                {"name": name, "tools": host.registry.tool_count(name), "mode": _server_mode(name)}
                for name in host.registry.server_names()
            ],
            "errors": host.connection_errors(),
        }
    )


def _json_response(data: dict):
    from starlette.responses import JSONResponse

    return JSONResponse(data)


async def chat_ws(websocket: WebSocket) -> None:
    assert host is not None
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "ready",
            "servers": [
                {"name": name, "tools": host.registry.tool_count(name), "mode": _server_mode(name)}
                for name in host.registry.server_names()
            ],
            "errors": host.connection_errors(),
        }
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                text = payload["text"]
            except (json.JSONDecodeError, KeyError, TypeError):
                await websocket.send_json({"type": "error", "message": "Malformed message"})
                continue
            if not text.strip():
                continue

            queue: asyncio.Queue = asyncio.Queue()
            _frame_subscribers.append(queue)
            turn_task = asyncio.create_task(host.agent_loop.run_turn(text))
            try:
                while not turn_task.done():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=0.05)
                        await websocket.send_json(event)
                    except asyncio.TimeoutError:
                        continue
                while not queue.empty():
                    await websocket.send_json(queue.get_nowait())

                try:
                    reply = await turn_task
                    await websocket.send_json({"type": "assistant_message", "text": reply})
                except Exception as exc:  # noqa: BLE001 - keep the socket alive
                    await websocket.send_json({"type": "error", "message": str(exc)})
            finally:
                _frame_subscribers.remove(queue)
    except WebSocketDisconnect:
        pass


app = Starlette(
    routes=[
        Route("/", index),
        Route("/api/status", status),
        WebSocketRoute("/ws", chat_ws),
        Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
    ],
    lifespan=lifespan,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("WEB_PORT", 8000)))
