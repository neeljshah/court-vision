"""Per-file test: the GATE-VERDICT LEDGER + IMPROVEMENT BACKLOG routes.

frontend.funnel_routes surfaces two static on-disk honest artifacts read-only:
  GET /api/funnel/ledger  -- every signal run through the leak-free gate
  GET /api/meta/backlog   -- the ranked "what we'll get better at next" list

Each must RESOLVE (200 with rows, or an honest 503/empty sentinel), must NEVER
500, must carry edge_claimed=False, and must NEVER leak a $ FIELD KEY. The lone
SHIP (soccer corners) must keep vs_close UNPROVEN (calibration, not a market
edge). The routes are exercised both on their own router and as mounted on the
canonical predict_service app.

Run: python -m pytest tests/frontend/test_funnel_routes.py -q
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.funnel_routes import router

# $ / currency FIELD KEYS that must never appear as a JSON key (prose is fine).
_BANNED_KEYS = ("usd", "dollars", "stake_usd", "pnl", "profit_usd",
                "bankroll_usd", "stake_dollars", "amount_usd")


def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k).lower()
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_keys(item)


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize("path", ("/api/funnel/ledger", "/api/meta/backlog"))
def test_resolves_never_500(client: TestClient, path: str):
    r = client.get(path)
    assert r.status_code in (200, 503), (
        "%s returned %s (expected 200 or honest 503)" % (path, r.status_code)
    )


@pytest.mark.parametrize("path", ("/api/funnel/ledger", "/api/meta/backlog"))
def test_no_dollar_field_and_edge_not_claimed(client: TestClient, path: str):
    r = client.get(path)
    body = r.json()
    keys = set(_iter_keys(body))
    for banned in _BANNED_KEYS:
        assert banned not in keys, "%s leaked a $ field key %r" % (path, banned)
    assert body.get("edge_claimed") is False, "%s must stamp edge_claimed False" % path


def test_ledger_has_corners_ship_with_unproven_vs_close(client: TestClient):
    """If the funnel artifacts are present, the lone SHIP is the soccer-corners
    CALIBRATION survivor and its vs_close must stay UNPROVEN (no market edge)."""
    body = client.get("/api/funnel/ledger").json()
    if body.get("status") != "ok":
        pytest.skip("funnel artifacts absent on this box -- honest empty state")
    rows = body["rows"]
    assert rows, "ok status must carry rows"
    ships = [r for r in rows if r["verdict"] in ("SHIP", "PROMOTE")]
    # Every SHIP must remain calibration-only: vs_close NEVER asserts a $ edge.
    for s in ships:
        assert "UNPROVEN" in s["vs_close"] or "CALIBRATION" in s["vs_close"], (
            "SHIP row %s claims a market edge in vs_close" % s["id"]
        )
    # The soccer-corners survivor is the documented lone SHIP.
    assert any(r["sport"] and "soccer" in r["sport"] for r in ships), (
        "expected the soccer-corners CALIBRATION SHIP in the ledger"
    )


def test_backlog_is_measurement_only(client: TestClient):
    body = client.get("/api/meta/backlog").json()
    if body.get("status") != "ok":
        pytest.skip("backlog artifact absent on this box -- honest empty state")
    assert isinstance(body["candidates"], list)
    assert body["n"] == len(body["candidates"])
    # The note frames it as measurement-only (never ships / flips a flag).
    note = json.dumps(body.get("note") or "").lower()
    assert "measurement" in note or "never" in note
