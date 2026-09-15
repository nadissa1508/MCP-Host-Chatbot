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

HELP_TEXT = """Comandos:
  /servers        lista los servidores MCP conectados y su cantidad de tools
  /tools          lista todas las tools disponibles, agrupadas por servidor
  /log [n]        muestra los últimos n frames MCP registrados (por defecto 10)
  /clear          borra el historial de la conversación
  /help           muestra este mensaje
  /quit           salir
Cualquier otro texto se envía al asistente."""


async def _prompt(loop: asyncio.AbstractEventLoop) -> str:
    return await loop.run_in_executor(None, input, "tú> ")


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
            print(f"  {server_name}: FALLÓ LA CONEXIÓN ({error})")
    elif name == "/tools":
        for tool in host.registry.to_anthropic_tools():
            print(f"  {tool['name']}: {tool['description']}")
    elif name == "/log":
        try:
            count = int(parts[1]) if len(parts) > 1 else 10
        except ValueError:
            print("Uso: /log [cantidad]")
            return True
        if count < 1:
            print("La cantidad debe ser un número entero mayor que cero.")
            return True
        entries = host.logger.recent(count)
        print(format_recent(entries) if entries else "(todavía no hay frames MCP registrados)")
    elif name == "/clear":
        host.conversation.clear()
        print("Conversación borrada.")
    else:
        print(f"Comando desconocido: {name}. Escribe /help para ver la lista de comandos.")
    return True


async def run() -> None:
    config = AppConfig.load()
    host = Host(config)
    print("Conectando con los servidores MCP...")
    await host.start()
    for server_name in host.registry.server_names():
        print(f"  conectado: {server_name} ({host.registry.tool_count(server_name)} tools)")
    for server_name, error in host.connection_errors().items():
        print(f"  no disponible: {server_name} ({error})")
    print("Listo. Escribe /help para ver los comandos, /quit para salir.\n")

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

            try:
                reply = await host.agent_loop.run_turn(text)
            except Exception as exc:  # noqa: BLE001 - keep the interactive session alive
                print(f"Error al procesar el mensaje: {exc}\n")
                continue
            print(f"asistente> {reply}\n")
    finally:
        await host.shutdown()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        # Ctrl+C is an expected way to leave an interactive terminal program.
        print("\nHasta luego.")

if __name__ == "__main__":
    main()
