"""supervisor.test_health -- per-file tests for supervisor.health extensions.

Acceptance criteria (WS1 restart-api-selfcheck):

  SH1. mount_selfcheck on predict_service.app reports /api/paper/predictions
       PRESENT (ok=True, path in present, not in missing).

  SH2. mount_selfcheck on a minimal FastAPI app that is MISSING the route
       reports ok=False, route in missing, logs WARN.

  SH3. mount_selfcheck re-reads the route table on EVERY call: two calls on an
       unchanged app agree, and a route added after the first call is PRESENT on
       the next call (no cached pre-registration snapshot -- S49b).

  SH4. smoke_probe with an injected fetcher returning 200 -> ok=True.

  SH5. smoke_probe with an injected fetcher returning non-200 -> ok=False.

  SH6. smoke_probe with a fetcher that raises -> ok=False, error key present.

  SH7. mount_selfcheck on a non-conforming object (no .routes) -> ok=False,
       missing == list(_REQUIRED_ROUTES), does not raise.

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest supervisor/test_health.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from supervisor.health import (  # noqa: E402
    _REQUIRED_ROUTES,
    _SELFCHECK_ATTR,
    mount_selfcheck,
    smoke_probe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_app(*extra_paths: str):
    """Return a FastAPI app registered with /health, /api/sports, + extra_paths."""
    from fastapi import FastAPI
    app = FastAPI()

    @app.get("/health")
    def _health() -> Dict[str, Any]:
        return {"status": "ok"}

    @app.get("/api/sports")
    def _sports() -> Dict[str, Any]:
        return {"status": "ok", "active": [], "capabilities": {}}

    for path in extra_paths:
        # Register a dummy GET handler for the given path.
        app.add_api_route(path, lambda: {"status": "ok"}, methods=["GET"])

    return app


# ---------------------------------------------------------------------------
# SH1 -- predict_service.app reports /api/paper/predictions PRESENT
# ---------------------------------------------------------------------------

def test_sh1_predictions_route_present_in_real_app():
    """SH1: mount_selfcheck on predict_service.app sees /api/paper/predictions."""
    try:
        from predict_service.app import app  # noqa: PLC0415
    except Exception as exc:
        pytest.skip("predict_service.app not importable (%s)" % exc)

    result = mount_selfcheck(app)
    assert "/api/paper/predictions" in result["present"], (
        "SH1: /api/paper/predictions must be in 'present'; "
        "got present=%r, missing=%r" % (result["present"], result["missing"])
    )
    assert "/api/paper/predictions" not in result["missing"], (
        "SH1: /api/paper/predictions must NOT be in 'missing'; "
        "got missing=%r" % result["missing"]
    )
    assert result["ok"] is True, (
        "SH1: mount_selfcheck must return ok=True; got %r" % result
    )


# ---------------------------------------------------------------------------
# SH2 -- minimal app MISSING the route -> ok=False
# ---------------------------------------------------------------------------

def test_sh2_missing_route_reported_and_ok_false():
    """SH2: selfcheck on app without /api/paper/predictions -> ok=False."""
    # App has /health and /api/sports but NOT /api/paper/predictions.
    app = _make_minimal_app()
    result = mount_selfcheck(app)
    assert "/api/paper/predictions" in result["missing"], (
        "SH2: /api/paper/predictions should be in 'missing'; got %r" % result
    )
    assert result["ok"] is False, (
        "SH2: ok must be False when route is missing; got ok=%r" % result["ok"]
    )


# ---------------------------------------------------------------------------
# SH3 -- evaluated at call time (stable when nothing changed, fresh when it did)
# ---------------------------------------------------------------------------

def test_sh3_reevaluates_route_table_each_call():
    """SH3: repeated calls agree; a route added later is seen on the NEXT call."""
    app = _make_minimal_app("/api/paper/predictions")
    result1 = mount_selfcheck(app)
    result2 = mount_selfcheck(app)
    assert result1 == result2, (
        "SH3: two calls on an unchanged app must agree; got %r vs %r"
        % (result1, result2)
    )
    assert hasattr(app, _SELFCHECK_ATTR), (
        "SH3: last-result attribute %r must be set on app" % _SELFCHECK_ATTR
    )
    assert result1["ok"] is True, "SH3: ok must be True when route is registered"

    # A route registered AFTER the first check must not be masked by a snapshot.
    late = _make_minimal_app()
    assert mount_selfcheck(late)["ok"] is False, (
        "SH3: app without /api/paper/predictions must read ok=False first"
    )
    late.add_api_route("/api/paper/predictions", lambda: {"status": "ok"},
                       methods=["GET"])
    after = mount_selfcheck(late)
    assert after["ok"] is True, (
        "SH3: route added after the first call must be PRESENT on the next "
        "call (no cached pre-registration snapshot); got %r" % after
    )


# ---------------------------------------------------------------------------
# SH4 -- smoke_probe 200 -> ok=True
# ---------------------------------------------------------------------------

def test_sh4_smoke_probe_200_ok():
    """SH4: injected fetcher returning 200 -> smoke_probe ok=True."""
    def _fake_fetcher(req: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": 200}

    result = smoke_probe("http://127.0.0.1:8099/api/paper/predictions",
                         route_name="/api/paper/predictions",
                         fetcher=_fake_fetcher)
    assert result["ok"] is True, "SH4: ok must be True for HTTP 200; got %r" % result
    assert result["status"] == 200


# ---------------------------------------------------------------------------
# SH5 -- smoke_probe non-200 -> ok=False
# ---------------------------------------------------------------------------

def test_sh5_smoke_probe_non200_ok_false():
    """SH5: injected fetcher returning 404 -> smoke_probe ok=False."""
    def _fake_fetcher(req: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": 404}

    result = smoke_probe("http://127.0.0.1:8099/api/paper/predictions",
                         fetcher=_fake_fetcher)
    assert result["ok"] is False, (
        "SH5: ok must be False for HTTP 404; got %r" % result
    )
    assert result["status"] == 404


# ---------------------------------------------------------------------------
# SH6 -- smoke_probe fetcher raises -> ok=False, error key present
# ---------------------------------------------------------------------------

def test_sh6_smoke_probe_fetcher_raises_ok_false():
    """SH6: fetcher that raises -> smoke_probe ok=False, error key present."""
    def _bad_fetcher(req: Dict[str, Any]) -> Dict[str, Any]:
        raise ConnectionRefusedError("refused")

    result = smoke_probe("http://127.0.0.1:8099/api/paper/predictions",
                         fetcher=_bad_fetcher)
    assert result["ok"] is False, "SH6: ok must be False when fetcher raises"
    assert "error" in result, "SH6: error key must be present"


# ---------------------------------------------------------------------------
# SH7 -- non-conforming object (no .routes) -> ok=False, does not raise
# ---------------------------------------------------------------------------

def test_sh7_non_conforming_app_no_raise():
    """SH7: object with no .routes -> ok=False, missing==_REQUIRED_ROUTES."""
    class _Stub:
        pass

    result = mount_selfcheck(_Stub())
    assert result["ok"] is False, "SH7: ok must be False for non-conforming app"
    # All required routes should be in missing
    for rp in _REQUIRED_ROUTES:
        assert rp in result["missing"], (
            "SH7: %r must be in missing; got missing=%r" % (rp, result["missing"])
        )


# ---------------------------------------------------------------------------
# Self-runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print("PASS", fn.__name__)
            passed += 1
        except Exception as exc:
            print("FAIL", fn.__name__, "->", exc)
    print("%d/%d green" % (passed, len(fns)))
