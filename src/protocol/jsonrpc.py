"""Hand-written JSON-RPC 2.0 message types, matching https://www.jsonrpc.org/specification.

No MCP-specific behaviour lives here: this module only knows how to build,
serialize and parse the four JSON-RPC message shapes (request, notification,
success response, error response) and validate them against the spec.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Union

from src.protocol.errors import JsonRpcError

JSONRPC_VERSION = "2.0"


class IdGenerator:
    """Produces unique, monotonically increasing request ids for one client."""

    def __init__(self, start: int = 1):
        self._counter = itertools.count(start)

    def next(self) -> int:
        return next(self._counter)


@dataclass
class JsonRpcRequest:
    """A call that expects a response, identified by `id`."""

    method: str
    id: int | str
    params: dict[str, Any] | list[Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        message: dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "id": self.id,
            "method": self.method,
        }
        if self.params is not None:
            message["params"] = self.params
        return message


@dataclass
class JsonRpcNotification:
    """A one-way call: no `id`, no response is ever sent for it."""

    method: str
    params: dict[str, Any] | list[Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        message: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": self.method}
        if self.params is not None:
            message["params"] = self.params
        return message


@dataclass
class JsonRpcResponse:
    """A successful reply, carrying `result` and echoing the request's `id`."""

    id: int | str | None
    result: Any = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "id": self.id, "result": self.result}


@dataclass
class JsonRpcErrorResponse:
    """A failed reply, carrying `error` and echoing the request's `id`."""

    id: int | str | None
    error: JsonRpcError

    def to_dict(self) -> dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "id": self.id, "error": self.error.to_dict()}


JsonRpcMessage = Union[JsonRpcRequest, JsonRpcNotification, JsonRpcResponse, JsonRpcErrorResponse]


def encode(message: JsonRpcMessage) -> dict[str, Any]:
    """Turn one of our message dataclasses into a plain JSON-serializable dict."""
    return message.to_dict()


def parse_message(raw: dict[str, Any]) -> JsonRpcMessage:
    """Parse a decoded JSON object into the matching JSON-RPC message type.

    Raises JsonRpcError(INVALID_REQUEST) if the object does not match any of
    the four valid shapes defined by the spec.
    """
    if not isinstance(raw, dict) or raw.get("jsonrpc") != JSONRPC_VERSION:
        raise JsonRpcError.invalid_request(raw)

    has_id = "id" in raw
    has_method = "method" in raw
    has_result = "result" in raw
    has_error = "error" in raw

    if has_method:
        if not isinstance(raw["method"], str) or has_result or has_error:
            raise JsonRpcError.invalid_request(raw)
        if "params" in raw and not isinstance(raw["params"], (dict, list)):
            raise JsonRpcError.invalid_request(raw)
        if has_id and not _is_valid_id(raw["id"]):
            raise JsonRpcError.invalid_request(raw)

    if has_result and has_error:
        raise JsonRpcError.invalid_request(raw)
    if has_id and not _is_valid_id(raw["id"]):
        raise JsonRpcError.invalid_request(raw)

    if has_method and has_id:
        return JsonRpcRequest(method=raw["method"], id=raw["id"], params=raw.get("params"))
    if has_method and not has_id:
        return JsonRpcNotification(method=raw["method"], params=raw.get("params"))
    if has_error and has_id:
        err = raw["error"]
        if (
            not isinstance(err, dict)
            or not isinstance(err.get("code"), int)
            or isinstance(err.get("code"), bool)
            or not isinstance(err.get("message"), str)
        ):
            raise JsonRpcError.invalid_request(raw)
        return JsonRpcErrorResponse(
            id=raw["id"],
            error=JsonRpcError(err["code"], err["message"], err.get("data")),
        )
    if has_result and has_id:
        return JsonRpcResponse(id=raw["id"], result=raw["result"])

    raise JsonRpcError.invalid_request(raw)


def _is_valid_id(value: Any) -> bool:
    """Return whether a value is permitted in a JSON-RPC id field."""
    return value is None or isinstance(value, str) or (
        isinstance(value, int) and not isinstance(value, bool)
    )
