"""Per-file test: predict_service.app -- the :8099 Auto-API.

Covers:
  * GET /health                       -> {"status": "ok"}
  * GET /api/sports                   -> active list + capabilities + honest_note
  * GET /api/predict/nba (ok case)    -> full envelope from a stubbed store
  * GET /api/predict/nba (unavailable)-> the unavailable sentinel, never fabricated
  * GET /api/predict/nba/{game_id}    -> single PredictionRecord projection
  * GET /api/paper/trail reachable    -> proves paper_routes is mounted at :8099

The store is stubbed via the app's PREDICT_SERVICE_STORE_DIR override: we point
the store root at a tmp_path and write a real envelope with store.save(), so the
endpoints exercise the genuine read path (no parallel stub).

Honesty invariant: no $ / edge / roi / profit key in any response body.

Run: python -m pytest tests/predict_service/test_app.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from predict_service import app as app_module
from predict_service import store
from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)

# The endpoint reads through store.read_latest with the real wall clock (no
# injectable now over HTTP); use a tipoff a few hours in the FUTURE so the served
# game is an upcoming 'pre' slate -- never demoted ok->stale by wall-clock drift.
_FUTURE_TIPOFF = (
    datetime.now(timezone.utc) + timedelta(hours=3)
).isoformat(timespec="seconds")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with the store rooted at tmp_path (stubbed canonical store)."""
    monkeypatch.setattr(app_module, "_store_out_dir", lambda: str(tmp_path))
    return TestClient(app_module.app), tmp_path


def _envelope(sport: str = "nba") -> SnapshotEnvelope:
    mkt = MarketRow(sport=sport, game_id="g1", market_type="moneyline",
                    side="home", odds=1.91, book="bk", devigged_prob=0.52,
                    captured_at="2026-06-18T00:00:00+00:00", is_close=True)
    pred = PredictionRecord(sport=sport, game_id="g1", home="NYK", away="SAS",
                            tipoff=_FUTURE_TIPOFF,
                            pregame_probs={"home_ml": 0.58}, markets=[mkt])
    edge = EdgeRow(game_id="g1", market_type="moneyline", side="home",
                   model_prob=0.58, market_prob=0.52, ev=0.11, tier="B")
    return SnapshotEnvelope(sport=sport, generated_at="2026-06-18T22:00:00+00:00",
                            status="ok", predictions=[pred], markets=[mkt],
                            edges=[edge])


# Fabricated money KEYS we must never emit. Checked as JSON object keys (with the
# quote+colon shape), not as bare substrings -- a matchup name like "Houston
# Astros" legitimately contains "ros" and must not trip the honesty guard.
_FORBIDDEN_KEYS = ("$edge", "roi", "profit", "dollar", "dollar_edge")


def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_keys(item)


def _assert_honest(body) -> None:
    keys = {str(k).lower() for k in _iter_keys(body)}
    for token in _FORBIDDEN_KEYS:
        assert token not in keys, "fabricated money key %r in response" % token


def test_health(client):
    cl, _ = client
    r = cl.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_sports(client):
    cl, _ = client
    r = cl.get("/api/sports")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["active"], list)
    assert isinstance(body["capabilities"], dict)
    assert "honest_note" in body
    # every active sport has a capability descriptor
    for sport in body["active"]:
        assert sport in body["capabilities"]
    _assert_honest(body)


def test_predict_nba_ok(client):
    cl, tmp = client
    store.save(_envelope("nba"), out_dir=tmp)
    r = cl.get("/api/predict/nba")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["sport"] == "nba"
    assert len(body["predictions"]) == 1
    assert body["predictions"][0]["game_id"] == "g1"
    _assert_honest(body)


def test_predict_nba_unavailable(client):
    cl, _ = client
    # nothing written -> unavailable sentinel, NOT a fabricated snapshot
    r = cl.get("/api/predict/nba")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["sport"] == "nba"
    assert body["predictions"] == []
    _assert_honest(body)


def test_predict_game_ok(client):
    cl, tmp = client
    store.save(_envelope("nba"), out_dir=tmp)
    r = cl.get("/api/predict/nba/g1")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["prediction"]["game_id"] == "g1"
    assert len(body["markets"]) == 1
    assert len(body["edges"]) == 1
    _assert_honest(body)


def test_predict_game_missing(client):
    cl, tmp = client
    store.save(_envelope("nba"), out_dir=tmp)
    r = cl.get("/api/predict/nba/does-not-exist")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    _assert_honest(body)


def test_paper_trail_mounted(client):
    """paper_routes must be reachable at the same path the UI calls."""
    cl, _ = client
    r = cl.get("/api/paper/trail")
    # reachable (mounted real router -> 200, or degraded sentinel -> 503),
    # never a 404 (which would mean it was not mounted at all).
    assert r.status_code in (200, 503)
    body = r.json()
    assert "trail" in body
    assert "status" in body
    _assert_honest(body)
