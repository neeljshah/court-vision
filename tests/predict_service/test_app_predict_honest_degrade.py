"""Per-file REGRESSION test: /api/predict/{sport}[/{game_id}] honest-degrade.

BUG (found by the endpoint contract matrix, fixed in predict_service/app.py):
the two core read handlers `predict_sport` and `predict_game` called
store.read_latest() WITHOUT the @honest_route wrapper. A store read that RAISED
at request time therefore leaked a raw 500 + Python TRACEBACK to the browser --
a crash, not an honest degradation. Every other mounted router already used
@honest_route; these two core handlers were the gap.

FIX: decorate both handlers with @honest_route(extra=...) so any unhandled
exception becomes the honest units-only {status:'unavailable', edge_claimed:False}
envelope (no stack, no $, no fabricated value).

This test poisons store.read_latest to raise and asserts the response is the
honest envelope -- never a 500 traceback.

Run: python -m pytest tests/predict_service/test_app_predict_honest_degrade.py -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from predict_service import app as app_module
from predict_service import store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "_store_out_dir", lambda: str(tmp_path))
    return TestClient(app_module.app)


def _poison(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("forced store failure")
    monkeypatch.setattr(store, "read_latest", _boom)


def _assert_no_stack_no_dollar(r):
    assert "Traceback (most recent call last)" not in r.text, (
        "a Python traceback leaked to the response body")
    # Never a raw 500 crash -- the honest envelope intercepts it (503).
    assert r.status_code in (200, 503), "status %d (expected honest degrade)" % (
        r.status_code)
    body = r.json()
    assert isinstance(body, dict)
    txt = r.text.lower()
    for tok in ('"pnl"', '"roi"', '"bankroll"', '"profit"', '"dollar', '"usd"'):
        assert tok not in txt, "money key %r in degraded body" % tok
    return body


def test_predict_sport_raises_degrades_to_honest_envelope(client, monkeypatch):
    _poison(monkeypatch)
    r = client.get("/api/predict/nba")
    body = _assert_no_stack_no_dollar(r)
    assert body["status"] == "unavailable"
    assert body["edge_claimed"] is False
    # shape-stable empty fields so the UI degrades on a familiar shape.
    assert body.get("predictions") == []
    assert body.get("markets") == []
    assert body.get("edges") == []


def test_predict_game_raises_degrades_to_honest_envelope(client, monkeypatch):
    _poison(monkeypatch)
    r = client.get("/api/predict/nba/g1")
    body = _assert_no_stack_no_dollar(r)
    assert body["status"] == "unavailable"
    assert body["edge_claimed"] is False
    assert body.get("prediction") is None
    assert body.get("markets") == []
    assert body.get("edges") == []


def test_happy_path_unchanged_when_store_ok(client):
    """The wrapper is transparent on the happy path: an empty store still yields
    the normal unavailable sentinel (status 200), NOT the 503 failure envelope."""
    r = client.get("/api/predict/nba")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"  # empty store sentinel, not a crash
    assert body["sport"] == "nba"
    assert body["predictions"] == []
