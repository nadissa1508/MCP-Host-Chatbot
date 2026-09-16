import json

from src.observability.mcp_log import MCPLogger
from src.observability.render import format_recent


def test_logger_persists_and_renders_all_json_rpc_message_kinds(tmp_path):
    logger = MCPLogger(log_dir=tmp_path)
    frames = [
        ("send", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        ("recv", {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}),
        ("send", {"jsonrpc": "2.0", "method": "notifications/initialized"}),
        (
            "recv",
            {"jsonrpc": "2.0", "id": 2, "error": {"code": -32601, "message": "missing"}},
        ),
    ]

    for direction, message in frames:
        logger.log_frame(direction, "pharmacy", message)
    path = logger.path
    entries = logger.recent(10)
    rendered = format_recent(entries)
    logger.close()

    assert [entry.kind() for entry in entries] == [
        "request",
        "response",
        "notification",
        "error",
    ]
    assert "SOLICITUD" in rendered
    assert "RESPUESTA" in rendered
    assert "NOTIFICACIÓN" in rendered
    persisted = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [item["kind"] for item in persisted] == [
        "request",
        "response",
        "notification",
        "error",
    ]
