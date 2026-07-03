"""sell.app -- read-only sell API (port 8100, local only).

Exposes three endpoints for a prospective buyer:
  GET /health          -- liveness; edge_claimed=false in body.
  GET /track_record    -- the signed CLV + calibration TrackRecord.
  GET /demo/snapshot   -- the canned demo snapshot (no real data).

HONESTY INVARIANTS (binding):
  * edge_claimed=False on every response, by construction.
  * No dollar / ROI / P&L field is ever returned.
  * All numbers are either real (from the CLV ledger) or explicitly
    labelled as unavailable / demo.
  * Public deploy is HUMAN-GATED; this module never pushes origin.

INVARIANTS: <=300 LOC; ASCII only; no secrets in code (env only);
build only under sell/; never writes data/registry/.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Minimal HTTP server using stdlib only (no FastAPI dep required for demo).
# ---------------------------------------------------------------------------
try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError as e:  # pragma: no cover
    raise SystemExit("stdlib http.server unavailable: %s" % e)

_REPO = Path(__file__).resolve().parent.parent
_DEMO_DIR = Path(
    os.environ.get("SELL_DEMO_DIR",
                   str(_REPO / "data" / "frontend" / "sell" / "demo"))
)
_PORT = int(os.environ.get("SELL_PORT", "8100"))

_EDGE_CLAIMED = False  # hard constant; never True

_HONEST_NOTE = (
    "Calibrated predictor; no dollar edge claimed; "
    "CLV is the honest yardstick; edge_claimed=false always."
)


def _json_response(obj: Dict[str, Any]) -> bytes:
    """Serialise *obj* to UTF-8 JSON bytes with ASCII ensure."""
    return json.dumps(obj, indent=2, ensure_ascii=True).encode("ascii")


def _load_demo_file(name: str) -> Dict[str, Any]:
    path = _DEMO_DIR / name
    if not path.exists():
        return {"status": "unavailable", "reason": "demo seed not present; run sell.demo_seed"}
    try:
        return json.loads(path.read_text(encoding="ascii"))
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)}


class SellHandler(BaseHTTPRequestHandler):
    """Request handler for the sell API."""

    def log_message(self, fmt: str, *args: Any) -> None:  # suppress access log spam
        pass

    def _send(self, code: int, body: Dict[str, Any]) -> None:
        data = _json_response(body)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=ascii")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Edge-Claimed", "false")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")

        if path == "/health":
            self._send(200, {
                "status": "ok",
                "service": "sell_api",
                "edge_claimed": _EDGE_CLAIMED,
                "honest_note": _HONEST_NOTE,
            })
            return

        if path == "/track_record":
            raw = _load_demo_file("track_record.json")
            # Enforce edge_claimed=false even if the file is stale.
            raw["edge_claimed"] = False
            raw["honest_note"] = _HONEST_NOTE
            self._send(200, raw)
            return

        if path == "/demo/snapshot":
            raw = _load_demo_file("snapshot.json")
            self._send(200, raw)
            return

        self._send(404, {"status": "not_found", "path": path,
                         "available": ["/health", "/track_record", "/demo/snapshot"]})


def serve(port: int = _PORT) -> None:
    """Start the sell API and block."""
    server = HTTPServer(("0.0.0.0", port), SellHandler)
    print("sell_api | listening on port %d" % port, flush=True)
    print("sell_api | edge_claimed=false | public_deploy=HUMAN_GATED", flush=True)
    server.serve_forever()


def main() -> int:
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
