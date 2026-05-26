"""
test_L23_dashboard.py — Tests for L23_status_dashboard.

Five tests covering:
1. get_dashboard_data with all paths missing → all 8 section keys present
2. render_dashboard_html with stub data → section headers in output
3. format_pnl color tokens
4. svg_sparkline shape
5. Smoke-test server (Flask or http.server) on ephemeral port
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import urllib.request
from typing import Any, Dict

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
_TESTS_DIR = pathlib.Path(__file__).resolve().parent
_EL_DIR = _TESTS_DIR.parent
_PROJECT = _EL_DIR.parent.parent
sys.path.insert(0, str(_PROJECT))

import scripts.execute_loop.L23_status_dashboard as D  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _empty_tmp() -> pathlib.Path:
    """Return a temp directory guaranteed to contain none of the target files."""
    return pathlib.Path(tempfile.mkdtemp())


def _stub_data() -> Dict[str, Any]:
    """Minimal data dict that exercises all render paths without real files."""
    return {
        "_meta": {
            "generated_at": "2026-05-25 12:00:00 UTC",
            "nba_date": "2026-05-25",
        },
        "bankroll": {
            "current": 100_000.0,
            "daily_pnl": 250.0,
            "weekly_pnl": -100.0,
            "last_updated": "2026-05-25T10:00:00Z",
            "kill_switch_active": False,
            "kill_switch_reason": "",
            "test_mode": False,
        },
        "positions": {"count": 3, "total_exposure": 1500.0},
        "edges": {
            "edges": [
                {"player": "LeBron James", "stat": "pts", "line": 26.5, "side": "over", "ev": 0.08},
                {"player": "Curry", "stat": "fg3m", "line": 3.5, "side": "over", "ev": 0.06},
            ],
            "source": "dk_slate",
            "file": "dk_2026-05-25_main.json",
        },
        "clv": {
            "latest_file": "clv_report_2026-05-25.json",
            "means": {"pts": 0.05, "reb": -0.02, "ast": 0.03},
            "history": {"pts": [0.04, 0.05, 0.06], "reb": [-0.01, -0.02], "ast": [0.03]},
        },
        "freshness": {
            "win_prob_metrics.json": {"days": 1, "exists": True},
            "prop_pergame_walk_forward.json": {"days": 8, "exists": True},
        },
        "health": {
            "data": {
                "overall_status": "ok",
                "checks": {
                    "models": {"status": "ok"},
                    "data_pipeline": {"status": "warn"},
                    "ledger": {"status": "ok"},
                },
            },
            "last_modified": 0,
        },
        "settlements": {
            "rows": [
                {"player": "Tatum", "stat": "pts", "line": 25.5, "side": "over",
                 "stake": 200.0, "pnl": 182.0, "status": "WON"},
                {"player": "AD", "stat": "reb", "line": 11.5, "side": "under",
                 "stake": 100.0, "pnl": -100.0, "status": "LOST"},
            ]
        },
    }


# ── test 1: all-missing sections ──────────────────────────────────────────────

def test_get_data_all_missing(monkeypatch):
    """With all paths redirected to empty tmp dir, every section key is present."""
    tmp = _empty_tmp()

    # Patch all path constants in the module
    monkeypatch.setattr(D, "_LEDGER", tmp)
    monkeypatch.setattr(D, "_MODELS", tmp)
    monkeypatch.setattr(D, "_DFS", tmp)
    monkeypatch.setattr(D, "_SNAPSHOTS", tmp)
    # Bust the module-level cache
    monkeypatch.setattr(D, "_CACHE", (0.0, {}))

    data = D.get_dashboard_data()

    required = {"bankroll", "positions", "edges", "clv", "freshness", "health", "settlements", "_meta"}
    assert required.issubset(data.keys()), f"Missing keys: {required - data.keys()}"

    # Non-_meta sections should report "missing" or contain empty results
    for key in required - {"_meta", "freshness"}:
        section = data[key]
        # Either explicit missing status, or a dict with a message
        assert isinstance(section, dict), f"{key} is not a dict"
        has_missing = section.get("status") in ("missing", "error")
        has_data = any(k in section for k in ("current", "count", "edges", "rows", "means", "data"))
        assert has_missing or has_data, f"{key} has neither status=missing nor recognizable data"


# ── test 2: rendered HTML contains section headers ────────────────────────────

def test_render_html_contains_headers():
    """render_dashboard_html with stub data must include all major section labels."""
    data = _stub_data()
    html = D.render_dashboard_html(data)

    assert isinstance(html, str), "render_dashboard_html must return str"
    assert len(html) > 200, "HTML output is suspiciously short"

    required_strings = ["Bankroll", "Edges", "CLV", "Health", "Positions", "Settlements"]
    for s in required_strings:
        assert s in html, f"'{s}' not found in rendered HTML"


# ── test 3: format_pnl color tokens ──────────────────────────────────────────

def test_format_pnl_colors():
    neg = D.format_pnl(-50.0)
    pos = D.format_pnl(50.0)
    zero = D.format_pnl(0.0)

    assert "#dc2626" in neg, f"Red color not in negative PnL span: {neg}"
    assert "#16a34a" in pos, f"Green color not in positive PnL span: {pos}"
    assert "#6b7280" in zero, f"Gray color not in zero PnL span: {zero}"

    # Also verify the spans contain dollar values
    assert "$50.00" in pos        # positive: +$50.00
    assert "50.00" in neg         # negative: $-50.00 or -$50.00
    assert "$0.00" in zero


# ── test 4: svg_sparkline shape ───────────────────────────────────────────────

def test_svg_sparkline_shape():
    values = [1.0, 2.0, 1.5, 3.0, 2.5]
    result = D.svg_sparkline(values, width=120, height=30)

    assert isinstance(result, str)
    assert "<svg" in result, "Must contain <svg tag"
    assert "<polyline" in result, "Must contain <polyline tag"
    assert 'stroke="' in result, "Must include stroke color attribute"

    # Edge cases — should not raise
    empty = D.svg_sparkline([])
    assert "<svg" in empty

    single = D.svg_sparkline([5.0])
    assert "<svg" in single

    # Upward trend → green
    up = D.svg_sparkline([1.0, 2.0, 3.0])
    assert "#16a34a" in up

    # Downward trend → red
    down = D.svg_sparkline([3.0, 2.0, 1.0])
    assert "#dc2626" in down


# ── test 5: server smoke test ─────────────────────────────────────────────────

def test_serve_smoke(monkeypatch):
    """Start server on ephemeral port, hit / and /api/data, then shut down."""
    import socket

    # Pick a free port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    free_port = sock.getsockname()[1]
    sock.close()

    # Monkeypatch get_dashboard_data to return stub so no real I/O
    monkeypatch.setattr(D, "_CACHE", (0.0, {}))
    monkeypatch.setattr(D, "get_dashboard_data", lambda: _stub_data())

    server_obj = None

    def _run():
        nonlocal server_obj
        # Try Flask first; fall back to stdlib
        try:
            from flask import Flask, Response  # type: ignore
            app = Flask("test_dashboard")

            @app.route("/")
            def index():
                return Response(D.render_dashboard_html(D.get_dashboard_data()), mimetype="text/html")

            @app.route("/api/data")
            def api_data():
                return Response(json.dumps(D.get_dashboard_data(), default=str), mimetype="application/json")

            # Store werkzeug server ref for shutdown
            import werkzeug.serving  # type: ignore
            srv = werkzeug.serving.make_server("127.0.0.1", free_port, app)
            server_obj = srv
            srv.serve_forever()
        except ImportError:
            import http.server

            class Handler(http.server.BaseHTTPRequestHandler):
                def log_message(self, fmt, *args):
                    pass

                def do_GET(self):
                    if self.path in ("/", ""):
                        body = D.render_dashboard_html(D.get_dashboard_data()).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(body)
                    elif self.path == "/api/data":
                        body = json.dumps(D.get_dashboard_data(), default=str).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(body)
                    else:
                        self.send_response(404)
                        self.end_headers()

            srv = http.server.HTTPServer(("127.0.0.1", free_port), Handler)
            server_obj = srv
            srv.serve_forever()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    # Wait for server to be ready (max 5 s)
    base_url = f"http://127.0.0.1:{free_port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{base_url}/", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    else:
        pytest.fail("Server did not start within 5 seconds")

    # Test GET /
    resp = urllib.request.urlopen(f"{base_url}/", timeout=5)
    assert resp.status == 200, f"Expected 200, got {resp.status}"
    body = resp.read().decode("utf-8")
    assert "Dashboard" in body, "'Dashboard' not found in HTML response"

    # Test GET /api/data
    resp2 = urllib.request.urlopen(f"{base_url}/api/data", timeout=5)
    assert resp2.status == 200
    payload = json.loads(resp2.read().decode("utf-8"))
    assert isinstance(payload, dict), "API response is not a JSON object"
    assert "_meta" in payload, "_meta key missing from API response"

    # Graceful shutdown
    if server_obj is not None:
        try:
            server_obj.shutdown()
        except Exception:
            pass


# ── test 6: atomic write replaces existing file ───────────────────────────────

def test_atomic_write_replaces_existing_file(tmp_path):
    """Second atomic write must overwrite v1 content with v2 content atomically."""
    target = tmp_path / "dashboard_snapshot.json"

    # Write v1
    v1 = {"version": 1, "status": "old"}
    D._atomic_write_json(target, v1)
    assert target.exists(), "v1 file must exist after first write"
    assert json.loads(target.read_text(encoding="utf-8"))["version"] == 1

    # Write v2 — must replace v1 entirely
    v2 = {"version": 2, "status": "new", "score": 42}
    D._atomic_write_json(target, v2)
    result = json.loads(target.read_text(encoding="utf-8"))
    assert result["version"] == 2, f"Expected version=2, got {result}"
    assert result["status"] == "new"

    # No stray .tmp files left behind
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Stray .tmp files remain: {tmp_files}"


# ── test 7: atomic write leaves original unchanged on failure ─────────────────

def test_atomic_write_no_partial_on_failure(tmp_path, monkeypatch):
    """If os.replace raises, the original file must be unchanged and .tmp cleaned up."""
    target = tmp_path / "status.html"

    # Establish original content
    original_content = "<html><body>v1</body></html>"
    D._atomic_write_text(target, original_content)
    assert target.read_text(encoding="utf-8") == original_content

    # Monkeypatch os.replace to simulate a failure (e.g., cross-device rename)
    real_replace = os.replace

    def _failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _failing_replace)

    # Attempt a second write — must raise and leave original intact
    with pytest.raises(OSError, match="simulated replace failure"):
        D._atomic_write_text(target, "<html><body>v2</body></html>")

    # Original untouched
    assert target.read_text(encoding="utf-8") == original_content, (
        "Original file was modified despite os.replace failure"
    )

    # .tmp file must have been cleaned up
    monkeypatch.setattr(os, "replace", real_replace)  # restore so glob can run
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Stray .tmp file not cleaned up: {tmp_files}"
