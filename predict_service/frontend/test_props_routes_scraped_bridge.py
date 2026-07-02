"""Per-file test: props_routes falls back to the scraped-book bridge when the
domain-model snapshot has no player_prop market rows (mlb/soccer_intl today).

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/test_props_routes_scraped_bridge.py -q
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from predict_service.frontend.props_routes import router
from predict_service.contracts import SnapshotEnvelope


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_falls_back_to_scraped_bridge_when_no_domain_markets():
    ok_env = SnapshotEnvelope(status="ok", sport="mlb", generated_at="2026-07-02T12:00:00Z",
                              predictions=[], markets=[], edges=[])
    scraped_body = {"status": "ok", "sport": "mlb", "rows": [{"player": "X"}],
                    "count": 1, "edge_claimed": False, "clv_is_proxy": True,
                    "source": "scraped_book_snapshot", "honest_note": "n/a"}
    with patch("predict_service.frontend.props_routes.store.read_latest", return_value=ok_env), \
         patch("predict_service.frontend.props_routes.build_scraped_props_response",
               return_value=scraped_body) as mock_bridge:
        client = TestClient(_app())
        r = client.get("/api/predict/props/mlb")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "scraped_book_snapshot"
    assert body["count"] == 1
    mock_bridge.assert_called_once_with("mlb")


def test_no_bridge_call_when_domain_markets_exist():
    """NBA (or any sport with real domain-pricer market rows) must never even
    attempt the bridge -- the existing pricer path stays untouched."""
    from predict_service.contracts import PredictionRecord, MarketRow

    market = MarketRow(sport="nba", game_id="g1", market_type="player_prop",
                       side="LeBron James:pts", line=25.5, book="fanduel",
                       devigged_prob=0.55)
    pred = PredictionRecord(sport="nba", game_id="g1", home="LAL", away="BOS",
                            markets=[market])
    ok_env = SnapshotEnvelope(status="ok", sport="nba", generated_at="2026-07-02T12:00:00Z",
                              predictions=[pred], markets=[], edges=[])
    with patch("predict_service.frontend.props_routes.store.read_latest", return_value=ok_env), \
         patch("predict_service.frontend.props_routes.build_scraped_props_response") as mock_bridge:
        client = TestClient(_app())
        r = client.get("/api/predict/props/nba")
    assert r.status_code == 200
    mock_bridge.assert_not_called()


def test_unavailable_when_no_domain_markets_and_no_scraped_snapshot():
    ok_env = SnapshotEnvelope(status="ok", sport="soccer_intl", generated_at="2026-07-02T12:00:00Z",
                              predictions=[], markets=[], edges=[])
    with patch("predict_service.frontend.props_routes.store.read_latest", return_value=ok_env), \
         patch("predict_service.frontend.props_routes.build_scraped_props_response",
               return_value=None):
        client = TestClient(_app())
        r = client.get("/api/predict/props/soccer_intl")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "UNAVAILABLE"
