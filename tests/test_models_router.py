"""Tests for prediction endpoints (API-01) — models_router.

TDD RED: these tests must fail before models_router.py is created.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Return a TestClient for the FastAPI app."""
    from api.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# /predictions/shot
# ---------------------------------------------------------------------------

def test_shot_probability_valid(client):
    """Valid params return probability float in [0, 1]."""
    with patch("api.models_router._get_shot_model") as mock_get:
        mock_model = MagicMock()
        mock_model.predict.return_value = 0.65
        mock_get.return_value = mock_model

        resp = client.get(
            "/predictions/shot",
            params={
                "defender_dist": 100.0,
                "shot_angle": 45.0,
                "fatigue_proxy": 0.3,
                "court_zone": "paint",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "probability" in body
    assert 0.0 <= body["probability"] <= 1.0


def test_shot_probability_missing_required(client):
    """Missing defender_dist or shot_angle returns 422."""
    resp = client.get("/predictions/shot", params={"shot_angle": 45.0})
    assert resp.status_code == 422


def test_shot_probability_invalid_court_zone_still_returns_200(client):
    """An unrecognised court_zone still succeeds (model falls back internally)."""
    with patch("api.models_router._get_shot_model") as mock_get:
        mock_model = MagicMock()
        mock_model.predict.return_value = 0.45
        mock_get.return_value = mock_model

        resp = client.get(
            "/predictions/shot",
            params={
                "defender_dist": 80.0,
                "shot_angle": 30.0,
                "court_zone": "unknown_zone",
            },
        )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /predictions/win
# ---------------------------------------------------------------------------

def test_win_probability_valid(client):
    """Valid params return win_probability float in [0, 1]."""
    with patch("api.models_router._get_win_model") as mock_get:
        mock_model = MagicMock()
        mock_model.predict.return_value = 0.72
        mock_get.return_value = mock_model

        resp = client.get(
            "/predictions/win",
            params={
                "convex_hull_area": 50000.0,
                "avg_inter_player_dist": 200.0,
                "scoring_run": 4,
                "possession_streak": 3,
                "swing_point": 0,
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "win_probability" in body
    assert 0.0 <= body["win_probability"] <= 1.0


def test_win_probability_missing_required(client):
    """Missing convex_hull_area returns 422."""
    resp = client.get(
        "/predictions/win",
        params={"avg_inter_player_dist": 200.0},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /predictions/player-impact
# ---------------------------------------------------------------------------

def test_player_impact_valid(client):
    """Valid params return dict with epa_per_100 key."""
    with patch("api.models_router._get_impact_model") as mock_get:
        mock_model = MagicMock()
        mock_model.predict.return_value = {"epa_per_100": 3.5}
        mock_get.return_value = mock_model

        resp = client.get(
            "/predictions/player-impact",
            params={"track_id": 1, "made_rate": 0.45, "shots_taken": 20},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "epa_per_100" in body


def test_player_impact_missing_required(client):
    """Missing track_id returns 422."""
    resp = client.get(
        "/predictions/player-impact",
        params={"made_rate": 0.45, "shots_taken": 20},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Route count sanity check
# ---------------------------------------------------------------------------

def test_models_router_has_three_routes():
    """Router must register exactly 3 GET routes."""
    from api.models_router import router
    assert len(router.routes) == 3
