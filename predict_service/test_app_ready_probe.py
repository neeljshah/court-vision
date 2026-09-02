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
  R6. S49b regression: a probe taken while a required router is NOT mounted
      reads 503 (fail-closed), and the NEXT probe -- after that router
      registers -- reads 200 ready. The selfcheck must evaluate the route table
      at probe time, never a snapshot cached before the routers mounted.

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
from supervisor.health import _SELFCHECK_ATTR

_BANNED = ("$", "pnl", "profit", "roi")
_TARGET = "/api/paper/predictions"


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


# R6 -----------------------------------------------------------------------
def test_ready_sees_router_mounted_after_the_first_probe():
    """S49b: a not_ready probe must not stick once the router registers.

    Reproduces the pod ordering on the REAL app: the required route is detached
    (the router has not mounted yet) -> the probe is 503 not_ready, which is the
    fail-closed contract. The route is then re-attached, as the paper routers do
    after module execution, and the NEXT probe must read 200 ready.
    """
    app = app_mod.app
    saved = [r for r in app.routes if getattr(r, "path", "") == _TARGET]
    assert saved, "%s must be mounted on the real app before this test" % _TARGET
    for route in saved:
        app.routes.remove(route)
    if hasattr(app, _SELFCHECK_ATTR):
        delattr(app, _SELFCHECK_ATTR)
    try:
        client = _client()
        first = client.get("/ready")
        assert first.status_code == 503, (
            "a genuinely missing required route must stay fail-closed; got %d"
            % first.status_code)
        assert first.json()["status"] == "not_ready"
        assert _TARGET in first.json()["selfcheck"]["missing"]
        _assert_no_money(first.json())

        for route in saved:  # the paper routers register AFTER the first probe
            app.routes.append(route)
        second = client.get("/ready")
        assert second.status_code == 200, (
            "probe after the router mounted must be ready, not a cached "
            "pre-registration snapshot; got %d %r"
            % (second.status_code, second.json()))
        body = second.json()
        assert body["status"] == "ready"
        assert _TARGET in body["selfcheck"]["present"]
        _assert_no_money(body)
    finally:
        for route in saved:
            if route not in app.routes:
                app.routes.append(route)
        if hasattr(app, _SELFCHECK_ATTR):
            delattr(app, _SELFCHECK_ATTR)
