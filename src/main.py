"""Terminal entrypoint for the MCP host chatbot.

Boots the Host (connecting every enabled MCP server), then runs a plain
read-eval-print loop: free text goes to the agent loop, lines starting with
"/" are host commands (listing servers/tools, showing the MCP frame log).
"""

from __future__ import annotations

import asyncio
import sys

from src.host.config import AppConfig
from src.host.host import Host
from src.observability.render import format_recent

# The Windows terminal's default codepage (cp1252) can't encode characters
# an LLM response is free to include (checkmarks, em dashes, emoji), which
# would otherwise crash the REPL mid-conversation.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HELP_TEXT = """Commands:
  /servers        list connected MCP servers and their tool counts
  /tools          list every available tool, namespaced by server
  /log [n]        show the last n logged MCP frames (default 10)
  /clear          clear the conversation history
  /help           show this message
  /quit           exit
Anything else is sent to the assistant."""


async def _prompt(loop: asyncio.AbstractEventLoop) -> str:
    return await loop.run_in_executor(None, input, "you> ")


async def _handle_command(host: Host, command: str) -> bool:
    """Returns False when the REPL should exit."""
    parts = command.split()
    name = parts[0]

    if name == "/quit":
        return False
    if name == "/help":
        print(HELP_TEXT)
    elif name == "/servers":
        for server_name in host.registry.server_names():
            print(f"  {server_name}: {host.registry.tool_count(server_name)} tool(s)")
        for server_name, error in host.connection_errors().items():
            print(f"  {server_name}: FAILED TO CONNECT ({error})")
    elif name == "/tools":
        for tool in host.registry.to_anthropic_tools():
            print(f"  {tool['name']}: {tool['description']}")
    elif name == "/log":
        count = int(parts[1]) if len(parts) > 1 else 10
        entries = host.logger.recent(count)
        print(format_recent(entries) if entries else "(no MCP frames logged yet)")
    elif name == "/clear":
        host.conversation.clear()
        print("Conversation cleared.")
    else:
        print(f"Unknown command: {name}. Type /help for a list of commands.")
    return True


async def run() -> None:
    config = AppConfig.load()
    host = Host(config)
    print("Connecting to MCP servers...")
    await host.start()
    for server_name in host.registry.server_names():
        print(f"  connected: {server_name} ({host.registry.tool_count(server_name)} tools)")
    for server_name, error in host.connection_errors().items():
        print(f"  unavailable: {server_name} ({error})")
    print("Ready. Type /help for commands, /quit to exit.\n")

    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                text = (await _prompt(loop)).strip()
            except EOFError:
                break
            if not text:
                continue
            if text.startswith("/"):
                if not await _handle_command(host, text):
                    break
                continue

            reply = await host.agent_loop.run_turn(text)
            print(f"assistant> {reply}\n")
    finally:
        await host.shutdown()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
