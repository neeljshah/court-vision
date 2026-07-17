"""Protocol-level tests for the CourtVision stdio MCP server.

Spawns the server as a real subprocess over stdio and drives the JSON-RPC
handshake: initialize -> tools/list -> tools/call. Also asserts the server
module imports LIGHT (no pandas) so a resident process stays small.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EXPECTED_TOOLS = {
    "ask", "scouting_report", "comparables", "matchup_preview", "win_probability",
    "injury_report", "analytics_receipts", "run_burst", "system_health",
}


def _roundtrip(requests):
    """Feed newline-delimited JSON-RPC requests to a fresh server subprocess,
    return the list of parsed response objects (notifications produce none)."""
    payload = "".join(json.dumps(r) + "\n" for r in requests)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.platformkit.mcp_server.server"],
        input=payload, capture_output=True, text=True, cwd=str(REPO), timeout=120,
    )
    out = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    return out, proc


def test_import_is_light_no_pandas():
    """Importing the server module must NOT drag in pandas (lazy handlers)."""
    code = (
        "import sys; import scripts.platformkit.mcp_server.server as s; "
        "assert 'pandas' not in sys.modules, sorted(m for m in sys.modules if 'pandas' in m); "
        "print('OK')"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, cwd=str(REPO), timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_initialize_and_tools_list():
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    out, proc = _roundtrip(reqs)
    assert proc.returncode == 0, proc.stderr
    # notification produced no response -> two responses for two ids
    by_id = {m.get("id"): m for m in out}
    init = by_id[1]["result"]
    assert init["serverInfo"]["name"] == "courtvision"
    assert init["protocolVersion"]
    tools = by_id[2]["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == EXPECTED_TOOLS, names
    # every tool carries a non-trivial description + inputSchema
    for t in tools:
        assert len(t["description"]) > 40, t["name"]
        assert t["inputSchema"]["type"] == "object"


def test_tools_call_ask_returns_envelope():
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "ask", "arguments": {"query": "what is the claim survival rate?"}}},
    ]
    out, proc = _roundtrip(reqs)
    assert proc.returncode == 0, proc.stderr
    call = {m.get("id"): m for m in out}[2]["result"]
    env = json.loads(call["content"][0]["text"])
    assert "status" in env and "category" in env


def test_analytics_receipts_system_map():
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "analytics_receipts", "arguments": {"kind": "system_map"}}},
    ]
    out, proc = _roundtrip(reqs)
    call = {m.get("id"): m for m in out}[2]["result"]
    env = json.loads(call["content"][0]["text"])
    assert "status" in env


def test_absent_artifact_is_no_data_not_protocol_error():
    """A tool whose backing artifact is missing must return a no_data envelope
    inside a valid JSON-RPC result, NOT a JSON-RPC error."""
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "injury_report",
                    "arguments": {"sport": "nba", "team_or_player": "__no_such_team_zzz__"}}},
    ]
    out, proc = _roundtrip(reqs)
    resp = {m.get("id"): m for m in out}[2]
    assert "result" in resp, resp  # not a protocol error
    env = json.loads(resp["result"]["content"][0]["text"])
    assert env["status"] in ("no_data", "not_supported", "refused", "ok"), env


def test_unknown_tool_is_protocol_error():
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
         "params": {"name": "does_not_exist", "arguments": {}}},
    ]
    out, proc = _roundtrip(reqs)
    resp = {m.get("id"): m for m in out}[9]
    assert "error" in resp, resp
