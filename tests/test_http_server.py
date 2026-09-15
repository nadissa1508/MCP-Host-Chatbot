import json

import httpx
import pytest

from src.servers.pharmacy.http_server import SESSION_HEADER, active_sessions, app


@pytest.fixture(autouse=True)
def clear_sessions():
    active_sessions.clear()
    yield
    active_sessions.clear()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _initialize(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {}},
        },
    )
    assert response.status_code == 200
    assert SESSION_HEADER in response.headers
    return response.headers[SESSION_HEADER]


def _parse_sse(body: str) -> dict:
    data_lines = [line[len("data:") :].strip() for line in body.splitlines() if line.startswith("data:")]
    return json.loads("\n".join(data_lines))


@pytest.mark.asyncio
async def test_initialize_returns_session_and_server_info(client):
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {}},
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    payload = _parse_sse(response.text)
    assert payload["result"]["serverInfo"]["name"] == "pharmacy-mcp"
    assert SESSION_HEADER in response.headers


@pytest.mark.asyncio
async def test_notification_gets_202_with_empty_body(client):
    session_id = await _initialize(client)
    response = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={SESSION_HEADER: session_id},
    )
    assert response.status_code == 202
    assert response.content == b""


@pytest.mark.asyncio
async def test_request_without_session_header_is_rejected(client):
    response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_json_returns_json_rpc_parse_error(client):
    response = await client.post(
        "/mcp",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_non_object_json_returns_invalid_request(client):
    response = await client.post("/mcp", json=["not", "an", "object"])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_invalid_initialize_does_not_create_session(client):
    response = await client.post(
        "/mcp",
        json={"jsonrpc": "1.0", "id": 1, "method": "initialize"},
    )
    assert response.status_code == 200
    assert SESSION_HEADER not in response.headers
    assert _parse_sse(response.text)["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_tools_list_with_valid_session(client):
    session_id = await _initialize(client)
    response = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers={SESSION_HEADER: session_id},
    )
    assert response.status_code == 200
    payload = _parse_sse(response.text)
    tool_names = {t["name"] for t in payload["result"]["tools"]}
    assert "assess_symptoms" in tool_names


@pytest.mark.asyncio
async def test_tools_call_success_and_error(client):
    session_id = await _initialize(client)
    headers = {SESSION_HEADER: session_id}

    ok = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "assess_symptoms", "arguments": {"symptoms": ["headache"]}},
        },
        headers=headers,
    )
    assert _parse_sse(ok.text)["result"]["isError"] is False

    bad = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_medication_details", "arguments": {"sku": "NOPE"}},
        },
        headers=headers,
    )
    assert _parse_sse(bad.text)["result"]["isError"] is True


@pytest.mark.asyncio
async def test_delete_terminates_session(client):
    session_id = await _initialize(client)
    headers = {SESSION_HEADER: session_id}

    delete_response = await client.delete("/mcp", headers=headers)
    assert delete_response.status_code == 204

    after = await client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 5, "method": "tools/list"}, headers=headers
    )
    assert after.status_code == 404


@pytest.mark.asyncio
async def test_delete_unknown_session_returns_not_found(client):
    response = await client.delete("/mcp", headers={SESSION_HEADER: "unknown"})
    assert response.status_code == 404
