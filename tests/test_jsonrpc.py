import pytest

from src.protocol.errors import INVALID_REQUEST, METHOD_NOT_FOUND, JsonRpcError
from src.protocol.framing import decode_frame, encode_frame
from src.protocol.jsonrpc import (
    IdGenerator,
    JsonRpcErrorResponse,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    parse_message,
)


def test_request_to_dict_includes_params():
    request = JsonRpcRequest(method="tools/list", id=1, params={"a": 1})
    assert request.to_dict() == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {"a": 1},
    }


def test_request_to_dict_omits_absent_params():
    request = JsonRpcRequest(method="ping", id=2)
    assert "params" not in request.to_dict()


def test_notification_has_no_id():
    notification = JsonRpcNotification(method="notifications/initialized")
    encoded = notification.to_dict()
    assert "id" not in encoded
    assert encoded["method"] == "notifications/initialized"


def test_response_round_trip():
    response = JsonRpcResponse(id=5, result={"ok": True})
    parsed = parse_message(response.to_dict())
    assert isinstance(parsed, JsonRpcResponse)
    assert parsed.id == 5
    assert parsed.result == {"ok": True}


def test_error_response_round_trip():
    error = JsonRpcErrorResponse(id=7, error=JsonRpcError.method_not_found("frobnicate"))
    parsed = parse_message(error.to_dict())
    assert isinstance(parsed, JsonRpcErrorResponse)
    assert parsed.error.code == METHOD_NOT_FOUND
    assert "frobnicate" in parsed.error.message


def test_parse_message_rejects_wrong_version():
    with pytest.raises(JsonRpcError) as exc_info:
        parse_message({"jsonrpc": "1.0", "id": 1, "method": "x"})
    assert exc_info.value.code == INVALID_REQUEST


def test_parse_message_rejects_shape_with_neither_result_nor_error():
    with pytest.raises(JsonRpcError) as exc_info:
        parse_message({"jsonrpc": "2.0", "id": 1})
    assert exc_info.value.code == INVALID_REQUEST


@pytest.mark.parametrize(
    "message",
    [
        {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {"code": -1, "message": "x"}},
        {"jsonrpc": "2.0", "id": True, "method": "ping"},
        {"jsonrpc": "2.0", "id": 1, "method": 123},
        {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": "invalid"},
        {"jsonrpc": "2.0", "id": 1, "method": "ping", "result": {}},
    ],
)
def test_parse_message_rejects_invalid_json_rpc_shapes(message):
    with pytest.raises(JsonRpcError) as exc_info:
        parse_message(message)
    assert exc_info.value.code == INVALID_REQUEST


def test_id_generator_is_monotonic_and_unique():
    ids = IdGenerator(start=1)
    values = [ids.next() for _ in range(5)]
    assert values == [1, 2, 3, 4, 5]


def test_framing_round_trip():
    message = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    frame = encode_frame(message)
    assert frame.endswith(b"\n")
    assert decode_frame(frame) == message


def test_decode_frame_raises_parse_error_on_bad_json():
    with pytest.raises(JsonRpcError) as exc_info:
        decode_frame("not json")
    assert exc_info.value.code == -32700
