"""Local entrypoint for the pharmacy MCP server: reads newline-delimited
JSON-RPC requests from stdin and writes responses to stdout.

Run as: python -m src.servers.pharmacy.stdio_server
"""

from __future__ import annotations

import sys

from src.protocol.errors import JsonRpcError
from src.protocol.framing import decode_frame, encode_frame
from src.servers.pharmacy.core.dispatcher import Dispatcher


def main() -> None:
    dispatcher = Dispatcher()
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            message = decode_frame(raw_line)
        except JsonRpcError:
            # Malformed input has no request id to reply to; skip the line.
            continue

        response = dispatcher.handle(message)
        if response is not None:
            sys.stdout.buffer.write(encode_frame(response))
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
