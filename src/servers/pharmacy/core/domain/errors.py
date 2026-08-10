"""Domain-level errors for the pharmacy server.

These are caught at the tool boundary and turned into MCP tool results with
isError=true, so the model sees the failure as part of the conversation
instead of the JSON-RPC call itself failing.
"""


class PharmacyError(Exception):
    pass
