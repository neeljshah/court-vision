"""CourtVision stdio MCP server.

The MCP `mcp` SDK is not installed in this env, so this is the documented
minimal stdio fallback: newline-delimited JSON-RPC 2.0 over stdin/stdout,
implementing `initialize`, `tools/list`, `tools/call`, and the `notifications/*`
no-ops. The MCP wire protocol IS just JSON-RPC 2.0 over stdio, so no protocol
library is required -- only the tool table in tools.py.

This module stays LIGHT on import: it imports only stdlib + the tool table
(which itself imports nothing heavy). Every backing engine module is
lazy-imported inside its handler, so a resident server holds <100MB until a
tool is actually called.

Run:  python -m scripts.platformkit.mcp_server.server
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict

from scripts.platformkit.mcp_server.tools import handler_for, tool_specs

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "courtvision", "version": "1.0.0"}
_INSTRUCTIONS = (
    "CourtVision fail-closed sports-intelligence engine. Route every question through the "
    "resolver (tool 'ask') or a typed tool; never answer from model memory. Honor envelope "
    "status verbatim: no_data=say NO_DATA, not_supported=stop, refused=refuse (edge/ROI "
    "language). Quote numbers exactly and cite source_artifact + as_of. No dollar-edge claims. "
    "See docs/AI_CONSUMER_CONTRACT.md."
)


def _result(rid: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def dispatch(msg: Dict[str, Any]) -> Dict[str, Any] | None:
    """Handle one JSON-RPC request; return a response dict, or None for a
    notification (no id -> no reply, per JSON-RPC)."""
    method = msg.get("method")
    rid = msg.get("id")
    if method == "initialize":
        return _result(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
            "instructions": _INSTRUCTIONS,
        })
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None  # notification: no response
    if method == "ping":
        return _result(rid, {})
    if method == "tools/list":
        return _result(rid, {"tools": tool_specs()})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        handler = handler_for(name)
        if handler is None:
            return _error(rid, -32602, "unknown tool: %s" % name)
        try:
            envelope = handler(params.get("arguments") or {})
        except Exception as exc:  # noqa: BLE001 -- surface as tool error, never crash the loop
            return _result(rid, {
                "content": [{"type": "text", "text": json.dumps(
                    {"status": "error", "note": "%s: %s" % (type(exc).__name__, exc)})}],
                "isError": True,
            })
        return _result(rid, {"content": [{"type": "text",
                                          "text": json.dumps(envelope, default=str)}]})
    if rid is None:
        return None  # unknown notification
    return _error(rid, -32601, "method not found: %s" % method)


def serve(stdin=None, stdout=None) -> None:
    """Blocking newline-delimited JSON-RPC loop."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        resp = dispatch(msg)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


if __name__ == "__main__":  # pragma: no cover
    serve()
