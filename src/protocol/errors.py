"""JSON-RPC 2.0 error codes and the exception type used to carry them."""

from __future__ import annotations

from typing import Any

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Reserved range for implementation-defined server errors (-32000 to -32099).
SERVER_ERROR = -32000
PRESCRIPTION_REQUIRED = -32001
UNKNOWN_PRODUCT = -32002


class JsonRpcError(Exception):
    """A JSON-RPC error, carrying the fields needed to build an error response."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def __str__(self) -> str:
        if self.data is None:
            return self.message
        return f"{self.message}: {self.data}"

    def to_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return error

    @classmethod
    def parse_error(cls, data: Any = None) -> "JsonRpcError":
        return cls(PARSE_ERROR, "Parse error", data)

    @classmethod
    def invalid_request(cls, data: Any = None) -> "JsonRpcError":
        return cls(INVALID_REQUEST, "Invalid Request", data)

    @classmethod
    def method_not_found(cls, method: str) -> "JsonRpcError":
        return cls(METHOD_NOT_FOUND, f"Method not found: {method}")

    @classmethod
    def invalid_params(cls, data: Any = None) -> "JsonRpcError":
        return cls(INVALID_PARAMS, "Invalid params", data)

    @classmethod
    def internal_error(cls, data: Any = None) -> "JsonRpcError":
        return cls(INTERNAL_ERROR, "Internal error", data)
