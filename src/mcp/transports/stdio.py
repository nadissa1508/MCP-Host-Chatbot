"""stdio transport: spawns a server as a subprocess and frames JSON over its
stdin/stdout using newline-delimited JSON (see src.protocol.framing).

The subprocess's stderr is not part of the protocol -- servers use it for
free-form logging -- so it is drained line by line into an optional sink
instead of being parsed as JSON-RPC.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from contextlib import suppress
from typing import Any, Callable

from src.mcp.transports.base import Transport
from src.protocol.errors import JsonRpcError
from src.protocol.framing import decode_frame, encode_frame


class StdioTransport(Transport):
    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stderr_sink: Callable[[str], None] | None = None,
    ):
        self._command = command
        self._args = args or []
        self._cwd = cwd
        self._env = env
        self._stderr_sink = stderr_sink
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task | None = None

    async def connect(self) -> None:
        # On Windows, CreateProcess needs the resolved *.cmd/*.exe path for
        # shims like npx/npm/uvx -- plain "npx" only works through a shell.
        # Python MCP servers must use the host's active virtual environment,
        # even when an unactivated shell would resolve "python" elsewhere.
        if self._command in {"python", "python3"}:
            executable = sys.executable
        else:
            executable = shutil.which(self._command) or self._command
        self._process = await asyncio.create_subprocess_exec(
            executable,
            *self._args,
            cwd=self._cwd,
            env=self._env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        while True:
            line = await self._process.stderr.readline()
            if not line:
                return
            if self._stderr_sink:
                self._stderr_sink(line.decode("utf-8", errors="replace").rstrip())

    async def send(self, message: dict[str, Any]) -> None:
        if not self.is_connected:
            raise ConnectionError("stdio transport is not connected")
        assert self._process is not None and self._process.stdin is not None
        self._process.stdin.write(encode_frame(message))
        await self._process.stdin.drain()

    async def receive(self) -> dict[str, Any] | None:
        if self._process is None or self._process.stdout is None:
            return None
        while True:
            line = await self._process.stdout.readline()
            if not line:
                return None
            try:
                return decode_frame(line)
            except JsonRpcError:
                # A malformed line is not EOF. Keep reading so one invalid
                # frame cannot make the client report that the server closed.
                continue

    async def close(self) -> None:
        if self._process is None:
            return
        if self._process.stdin is not None:
            self._process.stdin.close()
            with suppress(BrokenPipeError, ConnectionResetError):
                await self._process.stdin.wait_closed()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            await asyncio.gather(self._stderr_task, return_exceptions=True)
        if self._process.returncode is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(self._process.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            self._process.kill()
            await self._process.wait()
        self._process = None
        self._stderr_task = None

    @property
    def is_connected(self) -> bool:
        return self._process is not None and self._process.returncode is None
