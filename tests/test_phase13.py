"""test_phase13.py — Phase 13 FastAPI endpoint tests."""
import time

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_returns_200():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "model_status" in body
    assert isinstance(body["model_status"], dict)
    assert len(body["model_status"]) >= 4


def test_simulate_endpoint():
    r = client.post("/simulate", json={"team_a": "LAL", "team_b": "BOS", "n_sims": 50})
    assert r.status_code == 200
    body = r.json()
    assert "win_probability" in body or "home_win_prob" in body or "team_a_win_prob" in body, (
        f"Expected win probability key, got keys: {list(body.keys())}"
    )
    assert "player_distributions" in body


def test_props_endpoint():
    r = client.get("/props/LeBron James", params={"opp_team": "GSW"})
    assert r.status_code == 200
    body = r.json()
    # predict_props returns a dict; must contain at least pts, reb, ast
    assert isinstance(body, dict)
    # Tolerate either direct keys or nested under 'predictions'
    flat = body.get("predictions", body)
    for stat in ("pts", "reb", "ast"):
        assert stat in flat, f"Missing stat '{stat}' in response: {list(flat.keys())}"


def test_edge_endpoint():
    r = client.get("/edge/0022500001")
    assert r.status_code == 200
    body = r.json()
    assert "edges" in body
    assert isinstance(body["edges"], list)  # may be empty — that's valid


def test_cache_hit_faster():
    payload = {"team_a": "GSW", "team_b": "MIA", "n_sims": 100}
    # Warm cache
    client.post("/simulate", json=payload)
    # Cold timing (already cached, but measure second call)
    t0 = time.perf_counter()
    r = client.post("/simulate", json=payload)
    elapsed_cached = time.perf_counter() - t0

    assert r.status_code == 200
    # Re-run with different n_sims to get uncached (cold) reference
    payload2 = {"team_a": "GSW", "team_b": "MIA", "n_sims": 101}
    t1 = time.perf_counter()
    client.post("/simulate", json=payload2)
    elapsed_cold = time.perf_counter() - t1

    # Cached call must be at least 2x faster than uncached
    assert elapsed_cached * 2 <= elapsed_cold, (
        f"Cache hit ({elapsed_cached:.4f}s) not 2x faster than cold ({elapsed_cold:.4f}s)"
    )
