"""CourtVision MCP over Streamable HTTP.

Wraps the existing stdio dispatch() (server.py) behind a single POST /mcp
endpoint per the MCP Streamable HTTP transport: JSON-RPC request -> 200
application/json response; notification -> 202 empty. Stateless (no
Mcp-Session-Id), no server-initiated SSE stream (GET -> 405). This is what
claude.ai "custom connector" URLs speak, once fronted by an HTTPS tunnel
(see scripts/go_live/mcp_live.py).

Run:  python -m scripts.platformkit.mcp_server.http_server [--port 8765]
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.platformkit.mcp_server.server import dispatch

DEFAULT_PORT = 8765
MAX_BODY = 1_000_000  # 1MB -- tool args are tiny; reject anything bigger


def _handle_body(body: bytes):
    """Parse one HTTP body -> (status_code, response_json_or_None)."""
    try:
        msg = json.loads(body)
    except json.JSONDecodeError:
        return 400, {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": "parse error"}}
    # Spec allows batches; claude.ai sends single messages, but handling a
    # list is three lines.
    if isinstance(msg, list):
        responses = [r for r in (dispatch(m) for m in msg if isinstance(m, dict))
                     if r is not None]
        return (200, responses) if responses else (202, None)
    if not isinstance(msg, dict):
        return 400, {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32600, "message": "invalid request"}}
    resp = dispatch(msg)
    if resp is None:  # notification
        return 202, None
    # Echo the client's requested protocolVersion on initialize -- dispatch()
    # pins 2024-11-05, but Streamable HTTP clients negotiate 2025-03-26+ and
    # some reject a downgrade. The tool surface is identical across versions.
    if msg.get("method") == "initialize":
        want = (msg.get("params") or {}).get("protocolVersion")
        if isinstance(want, str) and want:
            resp["result"]["protocolVersion"] = want
    return 200, resp


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, payload=None) -> None:
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(code)
        if body:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(400, {"error": "missing or oversized body"})
            return
        code, payload = _handle_body(self.rfile.read(length))
        self._send(code, payload)

    def do_GET(self) -> None:  # noqa: N802
        # Health probe convenience; the MCP endpoint itself is POST-only.
        if self.path.rstrip("/") in ("", "/health"):
            self._send(200, {"ok": True, "server": "courtvision-mcp"})
        else:
            self._send(405, {"error": "POST JSON-RPC to this endpoint"})

    def do_DELETE(self) -> None:  # noqa: N802
        self._send(200, None)  # stateless: session delete is a no-op

    def log_message(self, fmt, *args):  # quiet -- runs as a background daemon
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    # On Windows SO_REUSEADDR lets a second process silently steal the port --
    # fail loudly instead so duplicate starts are visible.
    ThreadingHTTPServer.allow_reuse_address = False
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"[mcp-http] serving MCP streamable-http on http://127.0.0.1:{args.port}/mcp")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
