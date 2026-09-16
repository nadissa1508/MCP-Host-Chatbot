# Wireshark capture — how it was done

This documents how `captures/pharmacy-remote-capture.pcapng` was produced,
so the capture can be reproduced or extended. The full write-up (message
classification, OSI/TCP-IP layer analysis, screenshots) is in the project
report (`report/`); this file only covers the reproducible steps.

## Why this needs a key log file at all

`pharmacy-remote` is served over HTTPS (TLS 1.3). A plain capture only
shows `Application Data` records — the JSON-RPC payloads are invisible
until the TLS session is decrypted. `src/mcp/transports/streamable_http.py`
supports this: when the `SSLKEYLOGFILE` environment variable is set, the
`httpx.AsyncClient` used by `StreamableHttpTransport` is created with an
`ssl.SSLContext` whose `keylog_filename` points at that file, so every TLS
session's keys are logged in the standard NSS key log format. This is a
no-op in every other run — nothing changes unless the variable is set.

## Reproducing the capture

Requirements: [Wireshark](https://www.wireshark.org/) with the
[Npcap](https://npcap.com/) capture driver (installed separately on
Windows; the packet-capture GUI can't capture anything without it).

1. In Wireshark: **Edit → Preferences → Protocols → TLS → (Pre)-Master-Secret
   log filename**, point it at a file (e.g. `sslkeys.log` in the repo
   root — already gitignored, it holds session secrets and must never be
   committed).
2. Start a capture on the active network interface (the real
   Wi-Fi/Ethernet adapter, not the loopback one — the traffic goes out to
   the public internet).
3. Run the host with the same path set in `SSLKEYLOGFILE`, with
   `pharmacy-remote` enabled in `config/servers.json` (the default):

   ```powershell
   $env:SSLKEYLOGFILE = "C:\path\to\MCP-Host-Chatbot\sslkeys.log"
   python -m src.main
   ```
4. Send a message that triggers pharmacy tool calls, e.g. a symptom
   description with an allergy, so the model chains `assess_symptoms` →
   `search_medications` → `check_interactions` → `check_stock`.
5. Stop the capture. Filter on the remote host to cut the noise:
   `tls.handshake.extensions_server_name contains "run.app"` finds the
   `Client Hello`s; from there, right-click → **Follow → TLS Stream**
   (or **HTTP/2 Stream**, if Wireshark offers it) shows the whole
   decrypted exchange in order.
6. **File → Save As** → `.pcapng` into `captures/`.

## A wrinkle worth documenting

The pharmacy server's liveness route is `/status`, not the more
conventional `/healthz` — see
[`pharmacy-mcp-spec.md`](pharmacy-mcp-spec.md#running-the-server) for why:
Google's edge network (GFE) intercepts the exact path `/healthz` as a
reserved internal health-check path on Cloud Run and never forwards it to
the container, regardless of what the application defines. This was found
while debugging the deployment, before doing the Wireshark capture, by
comparing responses across a few paths against the live service.
