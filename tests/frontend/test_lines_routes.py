"""Per-file test: frontend.lines_routes -- /api/lines/* (BE-P1-01 + BE-P0-05).

Covers:
  * GET /api/lines/{sport}            -> all MarketRows (book/side/line/odds/
                                          captured_at/is_close) + game context
  * GET /api/lines/{sport} (no snap)  -> status='unavailable' (stale-never-green)
  * GET /api/lines/{sport}/{gid}/history -> tick series + is_close flag
  * NO $ / roi / pnl key in any response body

Run: python -m pytest tests/frontend/test_lines_routes.py -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from predict_service import app as app_module
from predict_service import store
from predict_service.contracts import MarketRow, PredictionRecord, SnapshotEnvelope

_FORBIDDEN = ("$edge", "roi", "profit", "pnl", "dollar", "bankroll", "stake_dollars")


def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _iter_keys(it)


def _assert_honest(body):
    keys = {str(k).lower() for k in _iter_keys(body)}
    for tok in _FORBIDDEN:
        assert tok not in keys, "forbidden money key %r in response" % tok


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # lines_routes resolves the store dir from this env var.
    monkeypatch.setenv("PREDICT_SERVICE_STORE_DIR", str(tmp_path))
    return TestClient(app_module.app), tmp_path


def _envelope(sport="nba"):
    m1 = MarketRow(sport=sport, game_id="g1", market_type="moneyline",
                   side="home", odds=1.91, book="bookA",
                   captured_at="2026-06-18T00:00:00+00:00", is_close=False)
    m2 = MarketRow(sport=sport, game_id="g1", market_type="moneyline",
                   side="away", odds=2.05, book="bookB",
                   captured_at="2026-06-18T00:00:00+00:00", is_close=True)
    pred = PredictionRecord(sport=sport, game_id="g1", home="NYK", away="SAS",
                            tipoff="2026-06-18T23:00:00+00:00",
                            pregame_probs={"home_ml": 0.58}, markets=[m1, m2])
    return SnapshotEnvelope(sport=sport, generated_at="2026-06-18T22:00:00+00:00",
                            status="ok", predictions=[pred], markets=[m1, m2])


def test_lines_board(client):
    cl, tmp = client
    store.save(_envelope("nba"), out_dir=tmp)
    r = cl.get("/api/lines/nba")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["count"] == 2
    rows = body["lines"]
    assert {x["book"] for x in rows} == {"bookA", "bookB"}
    assert {x["side"] for x in rows} == {"home", "away"}
    # game context denormalized onto each line for the board.
    assert all(x.get("home") == "NYK" for x in rows)
    assert any(x.get("is_close") for x in rows)
    _assert_honest(body)


def test_lines_unavailable_not_green(client):
    cl, _ = client
    r = cl.get("/api/lines/nba")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["lines"] == []
    _assert_honest(body)


def test_line_history_shape(client):
    cl, _ = client
    r = cl.get("/api/lines/nba/g1/history")
    assert r.status_code == 200
    body = r.json()
    # No captured history on a fresh box -> empty series, honestly flagged.
    assert body["sport"] == "nba"
    assert body["game_id"] == "g1"
    assert isinstance(body["ticks"], list)
    assert "is_close" in body
    assert "clv_is_proxy" in body
    assert body["status"] in ("ok", "unavailable")
    _assert_honest(body)
