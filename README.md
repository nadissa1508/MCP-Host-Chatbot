# MCP Host Chatbot

A terminal chatbot that acts as an MCP **host**: it talks to the Anthropic
Messages API over raw HTTP and coordinates multiple MCP **servers** —
official ones (Filesystem, Git) and a pharmacy assistant built for this
project — through a hand-written JSON-RPC 2.0 / MCP client. No MCP SDK is
used anywhere in this codebase; every request, response and notification is
built, framed and parsed by hand (see `src/protocol/` and `src/mcp/`).

Built for the CC3067 Redes course at UVG. This repository implements the course's project 1 'Usando un protocolo existente'.

## Features implemented in this delivery

- Chat with the LLM through the raw Anthropic Messages API (no `anthropic`
  SDK), with conversation history kept across turns.

- Full MCP client lifecycle over stdio (`initialize` →
  `notifications/initialized` → `tools/list` → `tools/call`), hand-rolled
  JSON-RPC 2.0 framing with no MCP/JSON-RPC library.

- Every MCP frame (request, response, notification, error) is logged to
  `logs/*.jsonl` and viewable in the terminal with `/log`.

- Connects to the official **Filesystem** and **Git** MCP servers.

- A custom **Pharmacy** MCP server (industry use case: OTC symptom triage,
  interaction/allergy checking, stock lookup, ordering) — spec in
  [`docs/pharmacy-mcp-spec.md`](docs/pharmacy-mcp-spec.md).

- The Pharmacy server also runs the exact same dispatcher over a
  hand-rolled **Streamable HTTP** transport (`http_server.py` +
  `StreamableHttpTransport`), with session negotiation and SSE responses,
  so it can run as a local subprocess or a remote container without the
  host's code changing — only `config/servers.json` differs. It is
  deployed and running on **Google Cloud Run**; see `pharmacy-remote` in
  `config/servers.json` and
  [`docs/pharmacy-mcp-spec.md`](docs/pharmacy-mcp-spec.md#streamable-http-endpoint).

- The communication between the host and the remote pharmacy server was
  captured and decrypted with Wireshark (TLS session keys logged via
  `SSLKEYLOGFILE`, supported in `StreamableHttpTransport`) and classified
  into sync/request/response messages, with a layer-by-layer (link,
  network, transport, application) breakdown — see
  [`docs/wireshark-capture.md`](docs/wireshark-capture.md) for how to
  reproduce the capture, `captures/` for the `.pcapng` and screenshots,
  and `report/` for the full write-up.

- A browser chatbot UI (`src/web/`, `python -m src.web.server`) wraps the
  same `Host`/`AgentLoop` behind a WebSocket, with a single chat whose
  theme switches live depending on which MCP server answers.

## Requirements

- Python 3.11+
- Node.js (for `npx`, used to launch the official Filesystem MCP server)
- An Anthropic API key 

## Install

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

```bash
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY
```

`config/servers.json` lists the MCP servers the host connects to on start.
This delivery is graded on the **remote** pharmacy server, so by default it
enables `filesystem`, `git` (local/stdio) and `pharmacy-remote` (Streamable
HTTP, pointed at the deployed Cloud Run service via `PHARMACY_REMOTE_URL` in
`.env`), and disables the local `pharmacy` entry. To run the pharmacy server
locally instead, flip `pharmacy` on and `pharmacy-remote` off — no code
changes needed either way, both entries drive the exact same `Dispatcher`.

## Run

```bash
python -m src.main
```

```
Connecting to MCP servers...
  connected: filesystem (14 tools)
  connected: git (12 tools)
  connected: pharmacy (7 tools)
Ready. Type /help for commands, /quit to exit.

you> I've had a runny nose and sore throat for 2 days, I'm 24, allergic to paracetamol...
```

### Commands

| Command | Description |
|---|---|
| `/servers` | list connected MCP servers and their tool counts |
| `/tools` | list every available tool, namespaced as `server__tool` |
| `/log [n]` | show the last `n` logged MCP frames (default 10) |
| `/clear` | clear the conversation history |
| `/help` | show the command list |
| `/quit` | exit |

Anything else is sent to the assistant.

## Web UI

The same `Host`/`AgentLoop` used by the terminal also runs behind a small
browser chatbot (`src/web/`): a Starlette app with one WebSocket for the
chat, wrapping the exact same agent loop with no changes to the MCP layer.

```bash
python -m src.web.server   # serves on http://0.0.0.0:8000
```

It's a single chat window whose theme switches live depending on which MCP
server is actually doing the work: blue/white and minimal for `filesystem`
and `git`, and a pharmacy-branded look (inspired by a real Guatemalan
pharmacy chain's site) the moment a `pharmacy`/`pharmacy-remote` tool call
happens — tool-call badges stream in as they occur, taken from the same
`on_frame` hook the terminal's `/log` command reads.

### Trying the remote (HTTP) pharmacy server locally

```bash
python -m src.servers.pharmacy.http_server   # serves on http://0.0.0.0:8080
```

Then set `PHARMACY_REMOTE_URL=http://127.0.0.1:8080/mcp` in `.env`, disable
`pharmacy`, and enable `pharmacy-remote` in `config/servers.json`. Running
`python -m src.main` again connects to the exact same pharmacy logic over
HTTP instead of stdio — see
[`docs/pharmacy-mcp-spec.md`](docs/pharmacy-mcp-spec.md#streamable-http-endpoint)
for the wire-level detail and the Docker build command.

## Project layout

```
src/
  protocol/    hand-written JSON-RPC 2.0 (messages, errors, stdio framing)
  mcp/         MCP semantics on top of JSON-RPC: lifecycle, tool models, transports
  llm/         raw Anthropic Messages API client
  observability/  MCP frame logging (JSONL) and terminal rendering
  host/        the host: config, tool registry, conversation, agent loop
  servers/pharmacy/  the custom MCP server: domain logic, data, dispatcher,
                     stdio_server.py (local) and http_server.py (remote)
  web/         browser chatbot UI: Starlette + WebSocket wrapping the Host
  main.py      terminal entrypoint
tests/         unit + integration tests (protocol, pharmacy tools, stdio and
               Streamable HTTP transports, the HTTP server itself)
docs/          pharmacy server spec, demo scripts, Wireshark capture how-to
report/        full project report (spec, Wireshark layer analysis, conclusions)
captures/      Wireshark .pcapng and screenshots
config/        MCP server registry (servers.json)
```

## Testing

```bash
pip install -r requirements.txt  # includes pytest / pytest-asyncio
python -m pytest
```

The suite covers JSON-RPC encode/decode and error handling, every pharmacy
domain rule (triage red flags, interaction/allergy blocking, prescription
enforcement, stock decrements), an end-to-end integration test that spawns
the real pharmacy stdio server as a subprocess and drives it through the
full MCP lifecycle, the Streamable HTTP server's session handling (via an
in-process ASGI client), and the Streamable HTTP client transport against
a real `uvicorn` instance on a loopback socket.

## Demo scripts

See [`docs/demo-scenarios.md`](docs/demo-scenarios.md) for the scripted
scenarios used in the presentation (general Q&A with context, Filesystem +
Git working together, pharmacy triage, the red-flag safety refusal, and the
prescription-only refusal).
