"""Per-file test: predict_service.honesty_mw -- runtime honesty linter (HL-P1).

Covers:
  * a CLEAN json response passes through unchanged (status + body intact)
  * a response carrying a banned $/roi key is BLOCKED -> 500 fail-closed sentinel
    (the poisoned body NEVER reaches the client)
  * the sentinel itself carries NO forbidden money key
  * a non-JSON (e.g. plain text) response passes through untouched
  * NEWLY ADDED (2026-06-19 honesty harden): each key added to _FORBIDDEN_MONEY_KEYS
    in the lane-H harden pass is explicitly caught:
      stake, total_stake, total_pnl, roi_pct, paper_roi, paper_pnl

Run: python -m pytest tests/predict_service/test_honesty_mw.py -q
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.testclient import TestClient

from predict_service.honesty_mw import HonestyLinterMiddleware

_FORBIDDEN = ("roi", "pnl", "$edge", "profit", "bankroll")


def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _iter_keys(it)


def _app():
    app = FastAPI()
    app.add_middleware(HonestyLinterMiddleware)

    @app.get("/clean")
    def clean():
        return {"status": "ok", "units": 1.0, "model_prob": 0.58}

    @app.get("/poison")
    def poison():
        # A fabricated dollar/roi key that must NEVER reach the client.
        return JSONResponse({"status": "ok", "roi": 0.18, "pnl": 315.41})

    @app.get("/text")
    def text():
        return PlainTextResponse("hello roi pnl")  # not json: passes through

    # -- Lane-H harden endpoints: one per newly-added key --

    @app.get("/poison_stake")
    def poison_stake():
        return JSONResponse({"status": "ok", "stake": 50.0})

    @app.get("/poison_total_stake")
    def poison_total_stake():
        return JSONResponse({"status": "ok", "total_stake": 100.0})

    @app.get("/poison_total_pnl")
    def poison_total_pnl():
        return JSONResponse({"status": "ok", "total_pnl": -12.5})

    @app.get("/poison_roi_pct")
    def poison_roi_pct():
        return JSONResponse({"status": "ok", "roi_pct": 0.08})

    @app.get("/poison_paper_roi")
    def poison_paper_roi():
        return JSONResponse({"status": "ok", "paper_roi": 0.12})

    @app.get("/poison_paper_pnl")
    def poison_paper_pnl():
        return JSONResponse({"status": "ok", "paper_pnl": 37.0})

    return app


def test_clean_passes_through():
    cl = TestClient(_app())
    r = cl.get("/clean")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_prob"] == 0.58


def test_poison_is_blocked_fail_closed():
    cl = TestClient(_app())
    r = cl.get("/poison")
    # FAIL CLOSED: the poisoned body is withheld; a 500 sentinel is served.
    assert r.status_code == 500
    body = r.json()
    assert body["status"] == "error"
    assert "violations" in body
    # The original poisoned values must be gone.
    keys = {str(k).lower() for k in _iter_keys(body)}
    # 'roi'/'pnl' only appear inside the violation DETAIL strings, never as keys.
    for tok in _FORBIDDEN:
        assert tok not in keys


def test_non_json_passes_through():
    cl = TestClient(_app())
    r = cl.get("/text")
    assert r.status_code == 200
    assert r.text == "hello roi pnl"


# ── Lane-H harden tests (2026-06-19): each newly-added key is caught ──────────

def _assert_blocked(client, path: str, key_name: str) -> None:
    """Assert the endpoint is fail-closed (500) and the sentinel has violations."""
    r = client.get(path)
    assert r.status_code == 500, (
        "Expected 500 fail-closed for key %r at %s, got %d" % (key_name, path, r.status_code)
    )
    body = r.json()
    assert body.get("status") == "error", "Sentinel must carry status=error"
    violations = body.get("violations", [])
    assert violations, "Sentinel must list at least one violation for key %r" % key_name


def test_stake_is_blocked():
    """Bare 'stake' key is a units-rail violation."""
    _assert_blocked(TestClient(_app()), "/poison_stake", "stake")


def test_total_stake_is_blocked():
    """'total_stake' key is a units-rail violation (token 'stake' + exact match)."""
    _assert_blocked(TestClient(_app()), "/poison_total_stake", "total_stake")


def test_total_pnl_is_blocked():
    """'total_pnl' key is a units-rail violation (token 'pnl' + exact match)."""
    _assert_blocked(TestClient(_app()), "/poison_total_pnl", "total_pnl")


def test_roi_pct_is_blocked():
    """'roi_pct' key is a units-rail violation (token 'roi' + exact match)."""
    _assert_blocked(TestClient(_app()), "/poison_roi_pct", "roi_pct")


def test_paper_roi_is_blocked():
    """'paper_roi' key is a units-rail violation (token 'roi' + exact match)."""
    _assert_blocked(TestClient(_app()), "/poison_paper_roi", "paper_roi")


def test_paper_pnl_is_blocked():
    """'paper_pnl' key is a units-rail violation (token 'pnl' + exact match)."""
    _assert_blocked(TestClient(_app()), "/poison_paper_pnl", "paper_pnl")
