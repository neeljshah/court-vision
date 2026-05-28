"""Tests for /live/{game_id} per-game projection panel."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── 1. Import smoke ──────────────────────────────────────────────────────────

def test_live_game_router_imports():
    """Module imports cleanly and exposes a `router` object."""
    from api import live_game_router

    assert live_game_router.router is not None


# ── helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


# ── 2-5. HTTP-level shape ────────────────────────────────────────────────────

def test_api_live_game_returns_200(client):
    """JSON endpoint responds 200 even with no data on disk."""
    r = client.get("/api/live/0042400317")
    assert r.status_code == 200


def test_api_live_game_payload_shape(client):
    """JSON payload exposes the documented contract."""
    r = client.get("/api/live/0042400317")
    j = r.json()
    for key in ("game_id", "date", "n_rows", "rows",
                "live_available", "pregame_loaded", "generated_at"):
        assert key in j, f"missing key: {key}"
    assert isinstance(j["rows"], list)
    assert j["game_id"] == "0042400317"


def test_live_game_html_renders(client):
    """HTML page returns 200 with text/html content type."""
    r = client.get("/live/0042400317")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_live_game_no_live_data_banner(client):
    """When live boxscore is missing, the warning banner is rendered."""
    # The default test game id won't have a live boxscore on disk.
    r = client.get("/live/0042400317")
    assert "No live boxscore" in r.text


# ── 6. Pace-projection math ──────────────────────────────────────────────────

def test_build_payload_minutes_parse(tmp_path, monkeypatch):
    """Pace-projection = current * (32 / minutes_played); verify MM:SS parsing."""
    from api import live_game_router as mod

    # Stub the consolidated odds + pregame loader so the player matches the live row.
    def fake_consolidate(date):
        return [{
            "game_id": "GAMETEST",
            "player": "Test Player",
            "stat": "pts",
            "line": 14.5,
            "books": [{"book": "dk", "display": "DraftKings", "over_price": -110}],
            "n_books": 1,
        }]

    def fake_load_pregame(game_id, date):
        return [{
            "player_id": 9999,
            "player": "Test Player",
            "team": "TST",
            "stat": "pts",
            "q50": 16.0,
            "q10": 8.0,
            "q90": 24.0,
            "sigma": 4.0,
        }]

    live_payload = {
        "players": [
            {"player_id": 9999, "player": "Test Player",
             "pts": 12, "minutes": "24:30"}
        ]
    }

    def fake_load_live(game_id):
        return live_payload

    monkeypatch.setattr(mod, "_load_pregame_for_game", fake_load_pregame)
    monkeypatch.setattr(mod, "_load_live_boxscore", fake_load_live)
    # consolidate is imported INSIDE _build_payload; patch the source module.
    import api._courtvision_odds as cv_odds
    monkeypatch.setattr(cv_odds, "consolidate", fake_consolidate)

    payload = mod._build_payload("GAMETEST", "2026-05-27")

    assert payload["n_rows"] == 1
    row = payload["rows"][0]

    # minutes "24:30" -> 24.5
    assert row["minutes_played"] == pytest.approx(24.5, abs=0.01)
    # pace = 12 * (32 / 24.5) = ~15.67
    assert row["pace_projected"] == pytest.approx(12 * 32.0 / 24.5, abs=0.01)
    # current came through
    assert row["current"] == 12
    # edge = pace - line = 15.67 - 14.5
    assert row["edge_vs_line"] == pytest.approx(row["pace_projected"] - 14.5, abs=0.01)
    assert payload["live_available"] is True


# ── 7. Resilience: no data on disk ───────────────────────────────────────────

def test_build_payload_resilient_no_data(monkeypatch):
    """With no parquet + no live cache + no consolidate hits, returns n_rows=0 cleanly."""
    from api import live_game_router as mod

    monkeypatch.setattr(mod, "_load_pregame_for_game", lambda gid, d: [])
    monkeypatch.setattr(mod, "_load_live_boxscore", lambda gid: None)

    import api._courtvision_odds as cv_odds
    monkeypatch.setattr(cv_odds, "consolidate", lambda d: [])

    payload = mod._build_payload("0000000000", "2026-05-27")
    assert payload["n_rows"] == 0
    assert payload["rows"] == []
    assert payload["live_available"] is False
    assert payload["pregame_loaded"] is False


# ── bonus: minutes parser unit ───────────────────────────────────────────────

def test_parse_minutes_variants():
    from api.live_game_router import _parse_minutes

    assert _parse_minutes(None) is None
    assert _parse_minutes("") is None
    assert _parse_minutes("24:30") == pytest.approx(24.5)
    assert _parse_minutes("12:00") == pytest.approx(12.0)
    assert _parse_minutes(18.5) == 18.5
    assert _parse_minutes("18.5") == pytest.approx(18.5)
    assert _parse_minutes("garbage") is None
