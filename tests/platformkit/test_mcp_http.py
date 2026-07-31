"""Per-file check for the MCP streamable-HTTP body handler (no sockets)."""
import json

from scripts.platformkit.mcp_server.http_server import _handle_body


def test_initialize_echoes_client_protocol_version():
    code, resp = _handle_body(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "t", "version": "0"}},
    }).encode())
    assert code == 200
    assert resp["result"]["protocolVersion"] == "2025-03-26"
    assert resp["result"]["serverInfo"]["name"] == "courtvision"


def test_tools_list_has_ask():
    code, resp = _handle_body(b'{"jsonrpc":"2.0","id":2,"method":"tools/list"}')
    assert code == 200
    assert any(t["name"] == "ask" for t in resp["result"]["tools"])


def test_notification_is_202_no_body():
    code, resp = _handle_body(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
    assert code == 202 and resp is None


def test_garbage_is_400():
    code, resp = _handle_body(b"not json")
    assert code == 400 and resp["error"]["code"] == -32700
