"""Per-file test: frontend.gate_routes + results_routes (BE-P1-06 + BE-P0-09).

Covers:
  * GET /api/gate/status   -> paper_only=True, real_money_enabled=False,
                              threshold present, default-DENY reasons
  * GET /api/results/{sport} -> settled finals list (injected fetch, offline)
  * a non-final game is NEVER reported as a result
  * NO $ / roi / pnl key in any response body

Run: python -m pytest tests/frontend/test_gate_results_routes.py -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from predict_service import app as app_module

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
def client():
    return TestClient(app_module.app)


def test_gate_status_default_deny(client):
    r = client.get("/api/gate/status")
    assert r.status_code in (200, 503)
    body = r.json()
    # The honest, conservative default: PAPER ONLY, real money disabled.
    assert body["paper_only"] is True
    assert body["real_money_enabled"] is False
    assert "threshold" in body
    assert "reasons" in body and isinstance(body["reasons"], list)
    _assert_honest(body)


def test_results_settled_finals(monkeypatch, client):
    from predict_service import results_finals

    board = {"events": [
        # completed final -> returned
        {"id": "1", "date": "2026-06-18T23:00:00Z", "competitions": [{
            "status": {"type": {"state": "post", "completed": True,
                                "shortDetail": "Final"}},
            "competitors": [
                {"homeAway": "home", "score": "101",
                 "team": {"displayName": "NYK"}},
                {"homeAway": "away", "score": "98",
                 "team": {"displayName": "SAS"}}],
        }]},
        # in-progress -> NEVER reported as a final
        {"id": "2", "date": "2026-06-19T01:00:00Z", "competitions": [{
            "status": {"type": {"state": "in", "completed": False}},
            "competitors": [
                {"homeAway": "home", "score": "40",
                 "team": {"displayName": "BOS"}},
                {"homeAway": "away", "score": "44",
                 "team": {"displayName": "MIA"}}],
        }]},
    ]}
    monkeypatch.setattr(results_finals, "_LEAGUE_PATH",
                        {"nba": "basketball/nba"})
    _real_finals = results_finals.finals  # capture before patching

    def _fake_finals(sport):
        return _real_finals(sport, fetch=lambda url: board)

    monkeypatch.setattr("predict_service.results_finals.finals", _fake_finals)
    r = client.get("/api/results/nba")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["count"] == 1
    rec = body["results"][0]
    assert rec["game_id"] == "1"
    assert rec["home_score"] == 101 and rec["away_score"] == 98
    assert rec["completed"] is True
    _assert_honest(body)
