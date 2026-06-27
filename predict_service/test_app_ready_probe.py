"""predict_service.test_app_ready_probe -- per-file test for the /ready probe.

Fix: m1_api_paper readiness depth. The supervisor's HTTP readiness probe only
checks /health -> 200, which stays green even if a required router failed to
mount. This test verifies the additive /ready endpoint runs
supervisor.health.mount_selfcheck so a broken route table reads not-ready (503)
while the existing /health 200 liveness contract is UNCHANGED.

  R1. /health still returns 200 {"status":"ok"} (supervisor contract intact).
  R2. /ready on a fully-mounted app returns 200 {"status":"ready", selfcheck.ok}.
  R3. /ready when mount_selfcheck reports a missing route returns 503
      {"status":"not_ready"} with the missing route surfaced.
  R4. /ready falls back to liveness-only 200 if mount_selfcheck is unavailable
      (it must never be MORE fragile than /health).
  R5. No $/pnl/profit/roi key in any /ready response (honesty rail).

Run (per-file only)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_app_ready_probe.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi/httpx not installed", allow_module_level=True)

import predict_service.app as app_mod

_BANNED = ("$", "pnl", "profit", "roi")


def _assert_no_money(body: Any) -> None:
    blob = str(body).lower()
    for tok in _BANNED:
        assert tok not in blob, "banned money token %r in /ready body: %r" % (tok, body)


def _client() -> TestClient:
    return TestClient(app_mod.app)


# R1 -----------------------------------------------------------------------
def test_health_contract_unchanged():
    """/health still returns 200 {"status":"ok"} -- supervisor contract intact."""
    r = _client().get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# R2 -----------------------------------------------------------------------
def test_ready_ok_when_routes_present():
    """A passing mount_selfcheck -> 200 {"status":"ready"} with selfcheck.ok."""
    ok_res: Dict[str, Any] = {"checked": ["/health"], "present": ["/health"],
                              "missing": [], "ok": True}
    with patch("supervisor.health.mount_selfcheck", return_value=ok_res):
        r = _client().get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["selfcheck"]["ok"] is True
    _assert_no_money(body)


# R3 -----------------------------------------------------------------------
def test_ready_not_ready_when_route_missing():
    """A failing mount_selfcheck (missing route) -> 503 not_ready, route surfaced."""
    bad_res: Dict[str, Any] = {
        "checked": ["/health", "/api/paper/predictions"],
        "present": ["/health"],
        "missing": ["/api/paper/predictions"],
        "ok": False,
    }
    with patch("supervisor.health.mount_selfcheck", return_value=bad_res):
        r = _client().get("/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert "/api/paper/predictions" in body["selfcheck"]["missing"]
    _assert_no_money(body)


# R4 -----------------------------------------------------------------------
def test_ready_falls_back_to_liveness_when_selfcheck_unavailable():
    """If mount_selfcheck raises, /ready degrades to 200 liveness-only (never 5xx).

    /ready must never be MORE fragile than /health -- a selfcheck failure only
    removes the *depth*, never the liveness signal.
    """
    with patch("supervisor.health.mount_selfcheck",
               side_effect=RuntimeError("selfcheck boom")):
        r = _client().get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["selfcheck"] == "unavailable"
    _assert_no_money(body)
