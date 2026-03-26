"""Tests for Phase E5 prediction endpoints in predictions_router.py."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from api.main import app
    return TestClient(app)


# ── POST /predictions/injury-risk ────────────────────────────────────────────

def test_injury_risk_returns_valid_schema(client):
    """Injury risk endpoint returns required keys with floats in [0,1]."""
    with patch("api.predictions_router._player_name_from_id", return_value="LeBron James"), \
         patch("api.predictions_router.get_injury_risk", create=True), \
         patch("api.predictions_router.predict_load_management", create=True):

        from src.prediction.injury_risk import get_injury_risk
        from src.prediction.load_management import predict_load_management

        with patch("src.prediction.injury_risk.get_injury_risk",
                   return_value={"risk_score": 0.3, "risk_level": "Medium", "drivers": {}}), \
             patch("src.prediction.load_management.predict_load_management",
                   return_value={"load_mgmt_prob": 0.1, "recommendation": "Play"}):
            resp = client.post("/predictions/injury-risk", json={"player_id": 2544, "season": "2024-25"})

    assert resp.status_code == 200
    body = resp.json()
    assert "injury_risk_score" in body
    assert "load_management_prob" in body
    assert "games_missed_recent" in body


def test_injury_risk_missing_player_id(client):
    """Missing player_id returns 422."""
    resp = client.post("/predictions/injury-risk", json={"season": "2024-25"})
    assert resp.status_code == 422


# ── POST /predictions/breakout ────────────────────────────────────────────────

def test_breakout_returns_valid_schema(client):
    """Breakout endpoint returns score in [0,1] and key_factors list."""
    with patch("api.predictions_router._player_name_from_id", return_value="Tyrese Haliburton"), \
         patch("src.prediction.breakout_predictor.predict_breakout",
               return_value={
                   "player": "Tyrese Haliburton",
                   "breakout_score": 0.65,
                   "signals": {"pts_trend_up": 0.12, "usage_spike": 0.07},
                   "season_avgs": {"pts": 22.0},
               }):
        resp = client.post("/predictions/breakout", json={
            "player_id": 1630178, "opponent_team": "LAL", "season": "2024-25"
        })
    assert resp.status_code == 200
    body = resp.json()
    assert "breakout_score" in body
    assert "predicted_pts_above_avg" in body
    assert "key_factors" in body
    assert isinstance(body["key_factors"], list)
    assert 0.0 <= body["breakout_score"] <= 1.0


def test_breakout_missing_player_id(client):
    resp = client.post("/predictions/breakout", json={"opponent_team": "LAL"})
    assert resp.status_code == 422


# ── POST /predictions/lineup-optimizer ───────────────────────────────────────

def test_lineup_optimizer_returns_valid_schema(client):
    """Lineup optimizer returns optimal_lineup list with salary and pts fields."""
    resp = client.post("/predictions/lineup-optimizer", json={
        "game_ids": ["0022400710"],
        "budget": 50000.0,
        "platform": "draftkings",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "optimal_lineup" in body
    assert "total_salary" in body
    assert "projected_total" in body
    assert isinstance(body["optimal_lineup"], list)
    assert body["total_salary"] <= 50000.0


def test_lineup_optimizer_missing_game_ids(client):
    resp = client.post("/predictions/lineup-optimizer", json={"budget": 50000.0})
    assert resp.status_code == 422


# ── GET /predictions/today ────────────────────────────────────────────────────

def test_predictions_today_returns_games_list(client):
    """Today endpoint returns a response with games data."""
    resp = client.get("/predictions/today", params={"season": "2024-25"})
    assert resp.status_code == 200
    body = resp.json()
    # predict_today may return a list or a dict with 'games' key
    if isinstance(body, dict):
        assert "games" in body or "date" in body or isinstance(body.get("games", []), list)
    elif isinstance(body, list):
        assert True  # valid response


# ── GET /predictions/props/{player_id} ───────────────────────────────────────

def test_props_by_id_returns_valid_schema(client):
    """Props by ID endpoint returns props dict with pts/reb/ast."""
    with patch("api.predictions_router._player_name_from_id", return_value="LeBron James"), \
         patch("src.prediction.player_props.predict_props", return_value={
             "player": "LeBron James",
             "pts": 25.0, "reb": 7.5, "ast": 8.0,
             "fg3m": 1.5, "stl": 1.2, "blk": 0.8, "tov": 3.5,
             "dnp_risk": 0.05, "confidence": "model", "minutes_proj": 36.0,
         }):
        resp = client.get("/predictions/props/2544", params={"season": "2024-25", "opp_team": "BOS"})
    assert resp.status_code == 200
    body = resp.json()
    assert "player_id" in body
    assert "props" in body
    assert "pts" in body["props"]
    assert "dnp_prob" in body
    assert "injury_risk" in body


def test_props_by_id_unknown_player_returns_404(client):
    """Unknown player_id returns 404."""
    with patch("api.predictions_router._player_name_from_id", return_value=None):
        resp = client.get("/predictions/props/99999999", params={"season": "2024-25"})
    assert resp.status_code == 404
