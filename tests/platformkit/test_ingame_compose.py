"""tests.platformkit.test_ingame_compose -- per-file tests for W4 (api-ingame).

Tests:
  1. compose() merge shape -- all three sources present.
  2. INSUFFICIENT_DATA CLV -- clv_status is never fabricated (always INSUFFICIENT_DATA).
  3. No fabricated CLV -- no $ field, no non-INSUFFICIENT_DATA clv_status.
  4. live_fn -> None degrade -- win_prob falls back, live_state is None.
  5. box_fn -> empty degrade -- players == [], game_meta.game_status == "UNAVAILABLE".
  6. boxscore_read.parse_cdn_payload() shape -- pure parse, no network.
  7. boxscore_routes GET /api/boxscore/nba/{game_id} via TestClient.
  8. boxscore_routes non-NBA degrade -- sport != "nba" -> UNAVAILABLE players=[].
  9. ingame_mounts /api/ingame/{sport}/{game_id}/full route registration.

Run:
  cd /c/Users/neelj/nba-ai-system &&
  python -m pytest tests/platformkit/test_ingame_compose.py -q
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest


# ===================================================================== helpers

def _make_live(state_diff: float = 3.0, frac: float = 0.5,
               p0: float = 0.55) -> dict:
    return {
        "sport": "nba", "game_id": "0022400001",
        "home": "LAL", "away": "BOS",
        "state_diff": state_diff, "frac_elapsed": frac, "p0": p0,
        "p0_source": "PRIOR", "status": "Q2 5:12",
    }


def _make_served(p_win: float = 0.58) -> dict:
    return {
        "p_win": p_win, "model": "base+prior(proven)", "sport": "nba",
        "verdict": "REPLICATED", "provenance": [],
    }


def _make_meta(status: str = "LIVE") -> dict:
    return {
        "game_id": "0022400001", "captured_at": "2026-06-19T00:00:00+00:00",
        "game_status": status, "period": 2, "clock": "5:12",
        "home_team": "LAL", "away_team": "BOS",
        "home_score": 58, "away_score": 55,
    }


def _make_player(name: str = "Player A", pts: int = 10, side: str = "home") -> dict:
    return {
        "player_id": 1, "name": name, "team": "LAL", "side": side,
        "min": 18.5, "pts": pts, "reb": 4, "ast": 2,
        "fg3m": 1, "stl": 0, "blk": 0, "tov": 1, "pf": 2,
    }


# ===================================================================== imports

from predict_service.ingame_compose import (
    compose,
    _CLV_INSUFFICIENT,
)


# ===================================================================== 1. merge shape

def test_compose_merge_shape():
    """compose() returns all required top-level keys when all sources succeed."""
    result = compose(
        sport="nba",
        game_id="0022400001",
        live_fn=lambda sport, gid, p0=None: _make_live(),
        box_fn=lambda gid: (_make_meta(), [_make_player()]),
        serve_fn=lambda sport, state_diff, frac_elapsed, p0: _make_served(),
        p0=0.55,
    )
    assert result["sport"] == "nba"
    assert result["game_id"] == "0022400001"
    assert result["edge_claimed"] is False
    assert "live_state" in result
    assert "win_prob" in result
    assert "game_meta" in result
    assert "players" in result
    assert "clv_status" in result
    assert "honest_note" in result

    # live_state fields
    ls = result["live_state"]
    assert ls is not None
    assert ls["state_diff"] == 3.0
    assert ls["frac_elapsed"] == 0.5

    # win_prob carries the served dict
    assert result["win_prob"]["p_win"] == 0.58

    # players list
    assert len(result["players"]) == 1

    # No $ field anywhere in the flat response keys
    for key in result:
        assert "$" not in key, f"$ field found: {key}"


# ===================================================================== 2 + 3. CLV honesty

def test_clv_always_insufficient_data():
    """clv_status is INSUFFICIENT_DATA regardless of live state."""
    for live_ret in [_make_live(), None]:
        result = compose(
            sport="nba", game_id="X",
            live_fn=lambda sport, gid, p0=None: live_ret,
            box_fn=lambda gid: (_make_meta(), []),
            serve_fn=lambda sport, state_diff, frac_elapsed, p0: _make_served(),
        )
        assert result["clv_status"] == _CLV_INSUFFICIENT, (
            f"Expected INSUFFICIENT_DATA, got {result['clv_status']!r}"
        )

def test_no_dollar_field_in_response():
    """Compose response must NEVER contain a $ key or dollar-amount field."""
    result = compose(
        sport="nba", game_id="0022400001",
        live_fn=lambda sport, gid, p0=None: _make_live(),
        box_fn=lambda gid: (_make_meta(), [_make_player()]),
        serve_fn=lambda sport, state_diff, frac_elapsed, p0: _make_served(),
    )
    dumped = json.dumps(result)
    assert '"$' not in dumped, "$ character found in compose response JSON"
    # Verify no field named 'roi', 'profit', 'dollar', 'pnl' either
    for bad in ("roi", "profit_", "dollar", "pnl", "winnings"):
        assert bad not in dumped.lower().split('"'), (
            f"Forbidden field hint '{bad}' found in compose response"
        )


# ===================================================================== 4. live degrade

def test_compose_live_none_degrade():
    """When live_fn returns None, live_state is None and win_prob uses p0 fallback."""
    result = compose(
        sport="nba", game_id="X",
        live_fn=lambda sport, gid, p0=None: None,
        box_fn=lambda gid: (_make_meta("PRE_GAME"), []),
        serve_fn=lambda sport, state_diff, frac_elapsed, p0: {
            "p_win": p0 if p0 is not None else 0.5,
            "model": "p0", "provenance": [],
        },
        p0=0.60,
    )
    assert result["live_state"] is None
    # serve_fn received state_diff=None, frac_elapsed=None -> model='p0'
    assert result["win_prob"]["model"] == "p0"
    assert result["clv_status"] == _CLV_INSUFFICIENT


# ===================================================================== 5. box degrade

def test_compose_box_empty_degrade():
    """When box_fn returns [], players is [] in response."""
    result = compose(
        sport="nba", game_id="X",
        live_fn=lambda sport, gid, p0=None: _make_live(),
        box_fn=lambda gid: (_make_meta("UNAVAILABLE"), []),
        serve_fn=lambda sport, state_diff, frac_elapsed, p0: _make_served(),
    )
    assert result["players"] == []
    assert result["game_meta"]["game_status"] == "UNAVAILABLE"


# ===================================================================== 6. boxscore_read parse

def test_parse_cdn_payload_shape():
    """parse_cdn_payload returns (GameMeta, players) with correct field types."""
    from scripts.platformkit.ingame.boxscore_read import parse_cdn_payload

    # Minimal synthetic CDN payload matching the real cdn.nba.com schema.
    payload = {
        "game": {
            "gameId": "0022400001",
            "gameStatus": 2,
            "period": 2,
            "gameClock": "PT05M42.00S",
            "homeTeam": {
                "teamTricode": "LAL",
                "score": "58",
                "players": [
                    {
                        "personId": "203999",
                        "name": "LeBron James",
                        "starter": "1",
                        "statistics": {
                            "minutes": "PT18M30.00S",
                            "points": "15",
                            "reboundsTotal": "5",
                            "assists": "4",
                            "threePointersMade": "2",
                            "steals": "1",
                            "blocks": "0",
                            "turnovers": "2",
                            "foulsPersonal": "1",
                        },
                    }
                ],
            },
            "awayTeam": {
                "teamTricode": "BOS",
                "score": "55",
                "players": [],
            },
        }
    }

    meta, players = parse_cdn_payload(payload, captured_at="2026-06-19T00:00:00+00:00")

    assert meta["game_id"] == "0022400001"
    assert meta["game_status"] == "LIVE"
    assert meta["home_team"] == "LAL"
    assert meta["home_score"] == 58
    assert meta["captured_at"] == "2026-06-19T00:00:00+00:00"

    assert len(players) == 1
    p = players[0]
    assert p["name"] == "LeBron James"
    assert p["pts"] == 15
    assert p["reb"] == 5
    assert p["ast"] == 4
    assert p["side"] == "home"
    assert p["team"] == "LAL"
    assert isinstance(p["min"], float)


# ===================================================================== 7. boxscore_routes TestClient

def test_boxscore_route_nba():
    """GET /api/boxscore/nba/{game_id} returns valid shape (mocked CDN)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from predict_service.frontend.boxscore_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Inject a synthetic payload via patch on fetch_box.
    fake_meta = _make_meta("LIVE")
    fake_players = [_make_player("Tatum", 20, "away")]

    with patch(
        "predict_service.frontend.boxscore_routes._fetch_box",
        return_value=(fake_meta, fake_players),
    ):
        resp = client.get("/api/boxscore/nba/0022400001")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sport"] == "nba"
    assert data["game_id"] == "0022400001"
    assert data["edge_claimed"] is False
    assert "game_meta" in data
    assert "players" in data
    assert len(data["players"]) == 1
    assert data["players"][0]["pts"] == 20


# ===================================================================== 8. non-NBA degrade

def test_boxscore_route_non_nba():
    """GET /api/boxscore/{sport}/{game_id} for non-NBA returns UNAVAILABLE + empty players."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from predict_service.frontend.boxscore_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    for sport in ("mlb", "soccer", "tennis"):
        resp = client.get(f"/api/boxscore/{sport}/XYZ123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["players"] == [], f"Expected empty players for {sport}"
        assert data["game_meta"]["game_status"] == "UNAVAILABLE"
        assert data["edge_claimed"] is False


# ===================================================================== 9. ingame_mounts /full route

def test_ingame_mounts_full_route():
    """/api/ingame/{sport}/{game_id}/full is registered and returns compose shape."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from predict_service import ingame_mounts

    app = FastAPI()

    # Patch store so it returns empty (no predictions).
    with patch("predict_service.ingame_mounts.store") as mock_store:
        mock_env = type("Env", (), {"status": "unavailable", "predictions": []})()
        mock_store.read_latest.return_value = mock_env

        # Patch compose_default to return a controlled response.
        controlled = {
            "sport": "nba", "game_id": "0022400001",
            "live_state": None,
            "win_prob": {"p_win": 0.5, "model": "p0", "provenance": []},
            "game_meta": {"game_status": "UNAVAILABLE"},
            "players": [],
            "clv_status": "INSUFFICIENT_DATA",
            "clv_note": "test",
            "honest_note": "test",
            "edge_claimed": False,
        }
        with patch(
            "predict_service.ingame_compose.compose_default",
            return_value=controlled,
        ):
            ingame_mounts.register(app)
            client = TestClient(app)
            resp = client.get("/api/ingame/nba/0022400001/full")

    assert resp.status_code == 200
    data = resp.json()
    assert data["clv_status"] == "INSUFFICIENT_DATA"
    assert data["edge_claimed"] is False
    assert data["sport"] == "nba"
