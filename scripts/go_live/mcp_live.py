"""scripts.go_live.mcp_live -- on-demand public URL for the CourtVision MCP.

Puts scripts/platformkit/mcp_server/http_server.py (streamable-HTTP MCP on
:8765) behind a cloudflared quick tunnel so anyone can add it to claude.ai
as a custom connector: Settings > Connectors > Add custom connector with
URL  https://<random>.trycloudflare.com/mcp

Same pattern + shared helpers as site_live.py (the webapp switch); this one
only manages the MCP process and its own tunnel. Fleet untouched.

Commands:
    python scripts/go_live/mcp_live.py up
    python scripts/go_live/mcp_live.py down
    python scripts/go_live/mcp_live.py status
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.go_live.site_live import (  # noqa: E402
    CACHE_DIR, CLOUDFLARED, TUNNEL_URL_RE, _quiet_popen,
    _resolve_via_powershell, kill_tracked_pid, pid_matches,
)

PORT = 8765
STATE_FILE = CACHE_DIR / "mcp_state.json"
SERVER_LOG = CACHE_DIR / "mcp_http.log"
TUNNEL_LOG = CACHE_DIR / "mcp_cloudflared.log"
INIT_MSG = json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                       "params": {"protocolVersion": "2025-03-26",
                                  "capabilities": {},
                                  "clientInfo": {"name": "mcp_live", "version": "0"}}})


def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def post_initialize(base: str, timeout: float = 5.0) -> bool:
    """POST an MCP initialize to base/mcp; True iff a JSON-RPC result comes back."""
    req = urllib.request.Request(f"{base}/mcp", data=INIT_MSG.encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return b'"result"' in resp.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if "getaddrinfo failed" not in str(exc):
            return False
        # Same VPN-DNS fallback as site_live: resolve via PowerShell, connect by IP.
        import socket
        from urllib.parse import urlsplit
        host = urlsplit(base).hostname
        ip = _resolve_via_powershell(host) if host else None
        if not ip:
            return False
        orig = socket.getaddrinfo
        socket.getaddrinfo = lambda h, *a, **k: orig(ip if h == host else h, *a, **k)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return b'"result"' in resp.read()
        except (urllib.error.URLError, OSError, TimeoutError):
            return False
        finally:
            socket.getaddrinfo = orig


def cmd_up(_args) -> int:
    state = read_state()
    if state.get("url") and post_initialize(state["url"]):
        print(f"[mcp_live] already live: {state['url']}/mcp")
        return 0

    server_pid = state.get("server_pid")
    if post_initialize(f"http://127.0.0.1:{PORT}"):
        # Something already answers locally; keep it (pid may be stale/unknown).
        if not (server_pid and pid_matches(server_pid, "http_server")):
            server_pid = None
    else:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        log_fh = open(SERVER_LOG, "w")
        proc = _quiet_popen(
            [sys.executable, "-m", "scripts.platformkit.mcp_server.http_server",
             "--port", str(PORT)],
            cwd=str(REPO_ROOT), env={**__import__("os").environ, "PYTHONPATH": "."},
            stdout=log_fh, stderr=subprocess.STDOUT,
        )
        server_pid = proc.pid
        print(f"[mcp_live] MCP http server starting (pid {server_pid}) ...")
        deadline = time.time() + 30
        while time.time() < deadline and not post_initialize(f"http://127.0.0.1:{PORT}"):
            time.sleep(1)
        if not post_initialize(f"http://127.0.0.1:{PORT}"):
            raise SystemExit(f"[mcp_live] :{PORT} never answered initialize -- see {SERVER_LOG}")

    TUNNEL_LOG.write_text("")
    log_fh = open(TUNNEL_LOG, "w")
    tunnel = _quiet_popen(
        [str(CLOUDFLARED), "tunnel", "--url", f"http://127.0.0.1:{PORT}", "--no-autoupdate"],
        stdout=log_fh, stderr=subprocess.STDOUT,
    )
    print(f"[mcp_live] cloudflared starting (pid {tunnel.pid}) ...")
    url = None
    deadline = time.time() + 30
    while time.time() < deadline and not url:
        match = TUNNEL_URL_RE.search(TUNNEL_LOG.read_text(errors="ignore"))
        url = match.group(0) if match else None
        time.sleep(1)
    if not url:
        raise SystemExit(f"[mcp_live] tunnel URL never appeared -- see {TUNNEL_LOG}")

    ok = False
    deadline = time.time() + 60
    while time.time() < deadline and not ok:
        ok = post_initialize(url)
        if not ok:
            time.sleep(3)
    if not ok:
        raise SystemExit(f"[mcp_live] {url}/mcp never answered initialize through the tunnel")

    STATE_FILE.write_text(json.dumps({
        "server_pid": server_pid, "tunnel_pid": tunnel.pid, "url": url,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2))
    print(f"[mcp_live] LIVE. claude.ai custom-connector URL:  {url}/mcp")
    print("[mcp_live] known limitation: quick-tunnel URL is random per session")
    return 0


def cmd_down(_args) -> int:
    state = read_state()
    if not state:
        print("[mcp_live] already down (no state)")
        return 0
    killed = []
    if state.get("tunnel_pid") and kill_tracked_pid(state["tunnel_pid"], "cloudflared"):
        killed.append(f"cloudflared pid {state['tunnel_pid']}")
    if state.get("server_pid") and kill_tracked_pid(state["server_pid"], "http_server"):
        killed.append(f"mcp http pid {state['server_pid']}")
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    print(f"[mcp_live] down. killed: {killed or 'none (already dead)'}")
    return 0


def cmd_status(_args) -> int:
    state = read_state()
    local = post_initialize(f"http://127.0.0.1:{PORT}", timeout=3)
    print(f"local :{PORT} MCP answering: {local}")
    if state.get("url"):
        print(f"public: {state['url']}/mcp (reachable={post_initialize(state['url'])})")
        print(f"started_at: {state.get('started_at')}")
    else:
        print("public: none (not live)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("up", help="start MCP http server + tunnel, print connector URL")
    sub.add_parser("down", help="stop tunnel + MCP http server")
    sub.add_parser("status", help="show state + live probes")
    args = parser.parse_args()
    return {"up": cmd_up, "down": cmd_down, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
