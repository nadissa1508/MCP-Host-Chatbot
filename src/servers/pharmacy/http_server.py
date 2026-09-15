"""Remote entrypoint for the pharmacy MCP server: exposes the same
transport-agnostic Dispatcher over Streamable HTTP instead of stdio, so the
identical business logic can run on Cloud Run (or any container host).

Run locally with: uvicorn src.servers.pharmacy.http_server:app --port 8080
"""

from __future__ import annotations

import json
import os
import uuid

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from src.protocol.errors import JsonRpcError
from src.protocol.jsonrpc import JsonRpcErrorResponse
from src.servers.pharmacy.core.dispatcher import Dispatcher

SESSION_HEADER = "Mcp-Session-Id"

dispatcher = Dispatcher()
active_sessions: set[str] = set()


def _sse(payload: dict) -> str:
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


async def mcp_endpoint(request: Request) -> Response:
    try:
        message = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        error = JsonRpcErrorResponse(id=None, error=JsonRpcError.parse_error())
        return JSONResponse(error.to_dict(), status_code=400)

    if not isinstance(message, dict):
        error = JsonRpcErrorResponse(id=None, error=JsonRpcError.invalid_request(message))
        return JSONResponse(error.to_dict(), status_code=400)

    is_initialize = message.get("method") == "initialize"
    session_id = request.headers.get(SESSION_HEADER)

    if not is_initialize:
        if not session_id or session_id not in active_sessions:
            return JSONResponse({"error": "unknown or missing MCP session"}, status_code=404)

    response = dispatcher.handle(message)

    headers = {}
    if is_initialize and response is not None and "result" in response:
        session_id = uuid.uuid4().hex
        active_sessions.add(session_id)
        headers[SESSION_HEADER] = session_id

    if response is None:
        # Notification: no result to report back.
        return Response(status_code=202, headers=headers)

    return Response(_sse(response), media_type="text/event-stream", headers=headers)


async def mcp_delete(request: Request) -> Response:
    session_id = request.headers.get(SESSION_HEADER)
    if not session_id or session_id not in active_sessions:
        return JSONResponse({"error": "unknown or missing MCP session"}, status_code=404)
    active_sessions.discard(session_id)
    return Response(status_code=204)


async def health(request: Request) -> Response:
    return PlainTextResponse("ok")


app = Starlette(
    routes=[
        Route("/mcp", mcp_endpoint, methods=["POST"]),
        Route("/mcp", mcp_delete, methods=["DELETE"]),
        Route("/status", health, methods=["GET"]),
    ]
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
