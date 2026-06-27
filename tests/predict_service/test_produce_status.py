"""Per-file test: predict_service.produce_status -- /api/produce/* (BE-P0-04).

Covers:
  * GET /api/produce/status   -> per-sport {generated_at, age_seconds, ok, n_games}
  * a fresh (no snapshot) sport reads ok=False (stale-never-green)
  * a written 'ok' snapshot reads ok=True with age_seconds>=0 and n_games>=1
  * POST /api/produce/refresh  -> 403 'disabled' by default (default-DENY)
  * POST /api/produce/refresh  -> runs produce_once when the env flag is set
  * NO $ / roi / pnl key in any response body

Run: python -m pytest tests/predict_service/test_produce_status.py -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from predict_service import app as app_module
from predict_service import produce_status as ps_module
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
    monkeypatch.setattr(app_module, "_store_out_dir", lambda: str(tmp_path))
    monkeypatch.setattr(ps_module, "_store_out_dir", lambda: str(tmp_path))
    # Deterministic active set so the test does not depend on the corpus.
    monkeypatch.setattr(ps_module, "_active_sports", lambda: ["nba"])
    return TestClient(app_module.app), tmp_path


def _envelope(sport="nba"):
    mkt = MarketRow(sport=sport, game_id="g1", market_type="moneyline",
                    side="home", odds=1.91, book="bk")
    pred = PredictionRecord(sport=sport, game_id="g1", home="NYK", away="SAS",
                            pregame_probs={"home_ml": 0.58}, markets=[mkt])
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return SnapshotEnvelope(sport=sport, generated_at=now, status="ok",
                            predictions=[pred], markets=[mkt])


def test_status_fresh_clone_not_green(client):
    cl, _ = client
    r = cl.get("/api/produce/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    nba = next(s for s in body["sports"] if s["sport"] == "nba")
    # No snapshot written -> ok MUST be False (stale-never-green rail).
    assert nba["ok"] is False
    assert nba["status"] == "unavailable"
    assert body["any_fresh"] is False
    _assert_honest(body)


def test_status_ok_after_produce(client):
    cl, tmp = client
    store.save(_envelope("nba"), out_dir=tmp)
    r = cl.get("/api/produce/status")
    body = r.json()
    nba = next(s for s in body["sports"] if s["sport"] == "nba")
    assert nba["ok"] is True
    assert nba["n_games"] == 1
    assert nba["age_seconds"] is not None and nba["age_seconds"] >= 0
    assert body["any_fresh"] is True
    _assert_honest(body)


def test_refresh_disabled_by_default(client, monkeypatch):
    cl, _ = client
    monkeypatch.delenv("PREDICT_SERVICE_REFRESH", raising=False)
    r = cl.post("/api/produce/refresh")
    assert r.status_code == 403
    body = r.json()
    assert body["status"] == "disabled"
    _assert_honest(body)


def test_refresh_runs_when_enabled(client, monkeypatch):
    cl, tmp = client
    monkeypatch.setenv("PREDICT_SERVICE_REFRESH", "1")
    calls = {}

    def _fake_once(sport, *, out_dir=None):
        calls[sport] = out_dir
        store.save(_envelope(sport), out_dir=out_dir)
        return "%s/latest.json" % sport

    monkeypatch.setattr(ps_module.produce, "produce_once", _fake_once)
    r = cl.post("/api/produce/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["n_refreshed"] == 1
    assert "nba" in calls
    _assert_honest(body)
