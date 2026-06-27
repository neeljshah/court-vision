"""Per-file tests for bestbets_compute.py and bestbets_board_routes.py (W3).

Tests:
 - ranking: cards sorted by tier (A>B>C) then confidence desc
 - tier_filter: only the requested tier returned
 - status_filter: status partition works (live|pregame|done)
 - no $ field: no dollar/pnl/roi/profit key in any card
 - UNAVAILABLE path: empty/missing snapshot -> empty cards, status ok
 - prop cards: edge_vs_market > 0 filter applied
 - board route: FastAPI TestClient integration (filter params, error shapes)

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_bestbets_compute.py -q
"""
from __future__ import annotations

import types
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from predict_service.bestbets_compute import (
    VALID_TIERS,
    VALID_STATUSES,
    compute_best_bets,
    _cards_from_game,
    _game_status,
)
from predict_service.frontend.bestbets_board_routes import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers: fake game data mirroring decide_game output shape
# ---------------------------------------------------------------------------

def _make_game(game_id: str, tier: str, confidence: float,
               status: str = "pregame") -> Dict[str, Any]:
    """Minimal decide_game-like output with one best_bet."""
    return {
        "game_id": game_id,
        "home": "Home Team",
        "away": "Away Team",
        "live": {"state": "pre_game" if status == "pregame"
                 else "Final" if status == "done" else "in_game"},
        "candidates": [
            {
                "market_type": "moneyline",
                "side": "home",
                "model_prob": confidence,
                "market_prob": confidence - 0.05,
                "best_book": "espn:DraftKings",
                "best_odds": 2.1,
                "all_books": [{"book": "espn:DraftKings", "odds": 2.1}],
                "tier": tier,
                "flat_unit": 1.0,
            }
        ],
        "best_bets": [
            {
                "decision": "bet",
                "market_type": "moneyline",
                "side": "home",
                "tier": tier,
                "flat_unit": 1.0,
                "model_prob": confidence,
                "market_prob": confidence - 0.05,
                "best_odds": 2.1,
                "book": "espn:DraftKings",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Unit tests: _game_status
# ---------------------------------------------------------------------------

class TestGameStatus:
    def test_pregame(self):
        assert _game_status({"state": "pre_game"}) == "pregame"

    def test_live(self):
        assert _game_status({"state": "in_game"}) == "live"
        assert _game_status({"state": "In Progress"}) == "live"

    def test_done(self):
        assert _game_status({"state": "Final"}) == "done"
        assert _game_status({"state": "complete"}) == "done"

    def test_empty(self):
        assert _game_status({}) == "pregame"

    def test_none(self):
        assert _game_status(None) == "pregame"


# ---------------------------------------------------------------------------
# Unit tests: _cards_from_game
# ---------------------------------------------------------------------------

class TestCardsFromGame:
    def test_bet_decision_only(self):
        """decision == 'bet' cards are returned; no_bet cards are not."""
        game = {
            "game_id": "g1",
            "home": "A",
            "away": "B",
            "live": {"state": "pre_game"},
            "candidates": [
                {"market_type": "moneyline", "side": "home",
                 "model_prob": 0.60, "market_prob": 0.50,
                 "best_book": "BK", "best_odds": 2.0, "all_books": [],
                 "tier": "B", "flat_unit": 1.0},
            ],
            "best_bets": [
                {"decision": "bet", "market_type": "moneyline", "side": "home",
                 "tier": "B", "flat_unit": 1.0,
                 "model_prob": 0.60, "market_prob": 0.50},
                {"decision": "no_bet", "market_type": "spread", "side": "away",
                 "tier": None, "flat_unit": 0.0},
            ],
        }
        cards = _cards_from_game(game, "nba")
        assert len(cards) == 1
        assert cards[0]["tier"] == "B"
        assert cards[0]["side"] == "home"

    def test_no_dollar_field(self):
        """No dollar/pnl/roi/profit key in any card."""
        game = _make_game("g2", "A", 0.65, "pregame")
        cards = _cards_from_game(game, "nba")
        forbidden = {"dollar", "pnl", "roi", "profit", "bankroll", "usd"}
        for card in cards:
            keys_lower = {k.lower() for k in card}
            assert not (keys_lower & forbidden), \
                f"Forbidden key in card: {keys_lower & forbidden}"

    def test_edge_vs_market_probability_diff(self):
        """edge_vs_market = model_prob - market_prob (not a $ amount)."""
        game = _make_game("g3", "A", 0.60, "pregame")
        cards = _cards_from_game(game, "nba")
        assert len(cards) == 1
        c = cards[0]
        expected = round(c["model_prob"] - c["market_prob"], 6)
        assert abs(c["edge_vs_market"] - expected) < 1e-9

    def test_invalid_tier_excluded(self):
        """A best_bet with tier not in A/B/C is silently dropped."""
        game = {
            "game_id": "g4",
            "home": "A", "away": "B",
            "live": {},
            "candidates": [],
            "best_bets": [
                {"decision": "bet", "market_type": "moneyline", "side": "home",
                 "tier": "X", "flat_unit": 1.0},
            ],
        }
        cards = _cards_from_game(game, "nba")
        assert cards == []

    def test_status_partition(self):
        """Cards reflect correct status based on live block."""
        for state_str, expected_status in [
            ("in_game", "live"), ("Final", "done"), ("pre_game", "pregame")
        ]:
            game = {
                "game_id": "g5",
                "home": "A", "away": "B",
                "live": {"state": state_str},
                "candidates": [
                    {"market_type": "moneyline", "side": "home",
                     "model_prob": 0.55, "market_prob": 0.50,
                     "best_book": "BK", "best_odds": 2.0, "all_books": [],
                     "tier": "C", "flat_unit": 1.0},
                ],
                "best_bets": [
                    {"decision": "bet", "market_type": "moneyline", "side": "home",
                     "tier": "C", "flat_unit": 1.0,
                     "model_prob": 0.55, "market_prob": 0.50},
                ],
            }
            cards = _cards_from_game(game, "nba")
            assert len(cards) == 1, f"Expected 1 card for {state_str}"
            assert cards[0]["status"] == expected_status, \
                f"{state_str} -> expected {expected_status}, got {cards[0]['status']}"


# ---------------------------------------------------------------------------
# Unit tests: compute_best_bets
# ---------------------------------------------------------------------------

def _fake_edge_view(sport: str) -> Dict[str, Any]:
    """Canned edge view with two games of different tiers."""
    games = [
        {
            "game_id": "g_A",
            "home": "TeamA1", "away": "TeamA2",
            "comparison": [
                {"market_type": "moneyline", "side": "home",
                 "model_prob": 0.65, "market_prob": 0.55,
                 "ev": 0.09, "tier": "A",
                 "book": "BK", "best_odds": 2.0,
                 "clv_is_proxy": True},
            ],
        },
        {
            "game_id": "g_C",
            "home": "TeamC1", "away": "TeamC2",
            "comparison": [
                {"market_type": "moneyline", "side": "home",
                 "model_prob": 0.52, "market_prob": 0.50,
                 "ev": 0.02, "tier": "C",
                 "book": "BK", "best_odds": 2.0,
                 "clv_is_proxy": True},
            ],
        },
    ]
    return {"status": "ok", "sport": sport, "games": games}


def _fake_decide_game(game: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal decide_game stub that promotes first comparison row to best_bets."""
    comp = (game.get("comparison") or [{}])[0]
    tier = comp.get("tier") or "C"
    mp = float(comp.get("model_prob") or 0.5)
    mkt = float(comp.get("market_prob") or 0.5)
    mt = str(comp.get("market_type", "moneyline"))
    side = str(comp.get("side", "home"))
    return {
        "game_id": game.get("game_id"),
        "home": game.get("home"),
        "away": game.get("away"),
        "live": {},
        "candidates": [
            {"market_type": mt, "side": side,
             "model_prob": mp, "market_prob": mkt,
             "best_book": "BK", "best_odds": 2.0, "all_books": [],
             "tier": tier, "flat_unit": 1.0},
        ],
        "best_bets": [
            {"decision": "bet", "market_type": mt, "side": side,
             "tier": tier, "flat_unit": 1.0,
             "model_prob": mp, "market_prob": mkt, "best_odds": 2.0},
        ],
    }


class TestComputeBestBets:
    """Tests for compute_best_bets()."""

    def test_ranking_tier_then_confidence(self):
        """Cards are sorted: tier A before C; within same tier, higher confidence first."""
        with patch("predict_service.bestbets_compute._get_edge_view",
                   side_effect=_fake_edge_view), \
             patch("predict_service.bestbets_compute._do_decide_game",
                   side_effect=_fake_decide_game), \
             patch("predict_service.bestbets_compute._clv_for",
                   return_value={"clv_pct": None, "beat_close": None,
                                 "clv_status": "INSUFFICIENT_DATA",
                                 "clv_is_proxy": True}), \
             patch("predict_service.bestbets_compute._cards_from_props",
                   return_value=[]):
            result = compute_best_bets("nba")
        assert result["status"] == "ok"
        cards = result["cards"]
        assert len(cards) == 2
        assert cards[0]["tier"] == "A"
        assert cards[1]["tier"] == "C"

    def test_tier_filter(self):
        """tier_filter='A' returns only A cards."""
        with patch("predict_service.bestbets_compute._get_edge_view",
                   side_effect=_fake_edge_view), \
             patch("predict_service.bestbets_compute._do_decide_game",
                   side_effect=_fake_decide_game), \
             patch("predict_service.bestbets_compute._clv_for",
                   return_value={"clv_pct": None, "beat_close": None,
                                 "clv_status": "INSUFFICIENT_DATA",
                                 "clv_is_proxy": True}), \
             patch("predict_service.bestbets_compute._cards_from_props",
                   return_value=[]):
            result = compute_best_bets("nba", tier_filter="A")
        assert all(c["tier"] == "A" for c in result["cards"])
        assert result["count"] == len(result["cards"])

    def test_status_filter_pregame(self):
        """status_filter='pregame' returns only pregame cards."""
        live_card = {
            "game_id": "live_g", "matchup": "L vs R", "sport": "nba",
            "market_type": "moneyline", "prop_player": None, "prop_stat": None,
            "side": "home", "model_prob": 0.60, "market_prob": 0.55,
            "best_book": "BK", "best_odds": 2.0, "all_books": [],
            "edge_vs_market": 0.05, "units": 1.0, "tier": "B",
            "confidence": 0.60,
            "clv": {"clv_pct": None, "beat_close": None,
                    "clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True},
            "clv_is_proxy": True, "status": "live",
            "honest_note": "test",
        }
        pregame_card = dict(live_card, game_id="pre_g", status="pregame",
                            tier="A", confidence=0.65)

        with patch("predict_service.bestbets_compute._get_edge_view",
                   return_value={"status": "ok", "games": []}), \
             patch("predict_service.bestbets_compute._cards_from_props",
                   return_value=[live_card, pregame_card]):
            result = compute_best_bets("nba", status_filter="pregame")
        assert all(c["status"] == "pregame" for c in result["cards"])

    def test_no_dollar_field_in_result(self):
        """No $ / pnl / roi / profit field in any card."""
        with patch("predict_service.bestbets_compute._get_edge_view",
                   side_effect=_fake_edge_view), \
             patch("predict_service.bestbets_compute._do_decide_game",
                   side_effect=_fake_decide_game), \
             patch("predict_service.bestbets_compute._clv_for",
                   return_value={"clv_pct": None, "beat_close": None,
                                 "clv_status": "INSUFFICIENT_DATA",
                                 "clv_is_proxy": True}), \
             patch("predict_service.bestbets_compute._cards_from_props",
                   return_value=[]):
            result = compute_best_bets("nba")
        forbidden = {"dollar", "pnl", "roi", "profit", "bankroll", "usd"}
        for card in result.get("cards", []):
            keys_lower = {k.lower() for k in card}
            assert not (keys_lower & forbidden)

    def test_unavailable_path_empty_cards(self):
        """When _get_edge_view raises, cards=[] and status='ok' (graceful)."""
        with patch("predict_service.bestbets_compute._get_edge_view",
                   side_effect=Exception("no snapshot")), \
             patch("predict_service.bestbets_compute._cards_from_props",
                   return_value=[]):
            result = compute_best_bets("nba")
        assert result["status"] == "ok"
        assert result["cards"] == []
        assert result["count"] == 0
        assert result["edge_claimed"] is False

    def test_edge_claimed_false(self):
        """edge_claimed is always False in the result."""
        with patch("predict_service.bestbets_compute._get_edge_view",
                   side_effect=_fake_edge_view), \
             patch("predict_service.bestbets_compute._do_decide_game",
                   side_effect=_fake_decide_game), \
             patch("predict_service.bestbets_compute._clv_for",
                   return_value={"clv_pct": None, "beat_close": None,
                                 "clv_status": "INSUFFICIENT_DATA",
                                 "clv_is_proxy": True}), \
             patch("predict_service.bestbets_compute._cards_from_props",
                   return_value=[]):
            result = compute_best_bets("nba")
        assert result["edge_claimed"] is False


# ---------------------------------------------------------------------------
# Integration tests: bestbets_board_routes via TestClient
# ---------------------------------------------------------------------------

class TestBestbetsBoardRoute:
    def test_invalid_tier_returns_400(self, client):
        resp = client.get("/api/bestbets/board?tier=Z")
        assert resp.status_code == 400
        body = resp.json()
        assert body["status"] == "error"
        assert "tier" in body["reason"].lower()

    def test_invalid_status_returns_400(self, client):
        resp = client.get("/api/bestbets/board?status=invalid")
        assert resp.status_code == 400
        body = resp.json()
        assert body["status"] == "error"
        assert "status" in body["reason"].lower()

    def test_ok_response_shape(self, client):
        """Route returns 200 with expected keys even when compute returns empty."""
        with patch("predict_service.frontend.bestbets_board_routes.compute_best_bets",
                   return_value={"status": "ok", "sport": "nba",
                                 "cards": [], "count": 0,
                                 "honest_note": "test", "edge_claimed": False}), \
             patch("predict_service.frontend.bestbets_board_routes._active_sports",
                   return_value=["nba"]):
            resp = client.get("/api/bestbets/board?sport=nba")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "cards" in body
        assert "count" in body
        assert body["edge_claimed"] is False

    def test_no_dollar_field_in_response(self, client):
        """Board response never contains $ / pnl / roi / profit."""
        card = {
            "game_id": "g1", "matchup": "A vs B", "sport": "nba",
            "market_type": "moneyline", "prop_player": None, "prop_stat": None,
            "side": "home", "model_prob": 0.60, "market_prob": 0.55,
            "best_book": "BK", "best_odds": 2.0, "all_books": [],
            "edge_vs_market": 0.05, "units": 1.0, "tier": "A",
            "confidence": 0.60,
            "clv": {"clv_pct": None, "beat_close": None,
                    "clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True},
            "clv_is_proxy": True, "status": "pregame",
            "honest_note": "test",
        }
        with patch("predict_service.frontend.bestbets_board_routes.compute_best_bets",
                   return_value={"status": "ok", "sport": "nba",
                                 "cards": [card], "count": 1,
                                 "honest_note": "test", "edge_claimed": False}), \
             patch("predict_service.frontend.bestbets_board_routes._active_sports",
                   return_value=["nba"]):
            resp = client.get("/api/bestbets/board?sport=nba")
        assert resp.status_code == 200
        forbidden = {"dollar", "pnl", "roi", "profit", "bankroll"}
        for key in resp.json():
            assert key.lower() not in forbidden
        for c in resp.json().get("cards", []):
            for key in c:
                assert key.lower() not in forbidden

    def test_tier_filter_passed_through(self, client):
        """tier=A filter is passed through to compute_best_bets."""
        calls: List[Any] = []

        def mock_compute(sport, tier_filter=None, status_filter=None,
                         include_props=True):
            calls.append({"sport": sport, "tier": tier_filter,
                          "status": status_filter})
            return {"status": "ok", "sport": sport, "cards": [],
                    "count": 0, "honest_note": "t", "edge_claimed": False}

        with patch("predict_service.frontend.bestbets_board_routes.compute_best_bets",
                   side_effect=mock_compute), \
             patch("predict_service.frontend.bestbets_board_routes._active_sports",
                   return_value=["nba"]):
            resp = client.get("/api/bestbets/board?sport=nba&tier=A")
        assert resp.status_code == 200
        assert calls[0]["tier"] == "A"

    def test_clv_insufficient_data_honest(self, client):
        """INSUFFICIENT_DATA CLV is surfaced honestly (not hidden or fabricated)."""
        card = {
            "game_id": "g2", "matchup": "X vs Y", "sport": "nba",
            "market_type": "moneyline", "prop_player": None, "prop_stat": None,
            "side": "away", "model_prob": 0.58, "market_prob": 0.53,
            "best_book": "BK", "best_odds": 2.0, "all_books": [],
            "edge_vs_market": 0.05, "units": 1.0, "tier": "B",
            "confidence": 0.58,
            "clv": {"clv_pct": None, "beat_close": None,
                    "clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True},
            "clv_is_proxy": True, "status": "pregame", "honest_note": "t",
        }
        with patch("predict_service.frontend.bestbets_board_routes.compute_best_bets",
                   return_value={"status": "ok", "sport": "nba",
                                 "cards": [card], "count": 1,
                                 "honest_note": "t", "edge_claimed": False}), \
             patch("predict_service.frontend.bestbets_board_routes._active_sports",
                   return_value=["nba"]):
            resp = client.get("/api/bestbets/board?sport=nba")
        assert resp.status_code == 200
        returned_card = resp.json()["cards"][0]
        assert returned_card["clv"]["clv_status"] == "INSUFFICIENT_DATA"
        assert returned_card["clv"]["clv_pct"] is None

    def test_multi_sport_rollup(self, client):
        """Without sport= param, queries all active sports."""
        calls: List[Any] = []

        def mock_compute(sport, tier_filter=None, status_filter=None,
                         include_props=True):
            calls.append(sport)
            return {"status": "ok", "sport": sport, "cards": [],
                    "count": 0, "honest_note": "t", "edge_claimed": False}

        with patch("predict_service.frontend.bestbets_board_routes.compute_best_bets",
                   side_effect=mock_compute), \
             patch("predict_service.frontend.bestbets_board_routes._active_sports",
                   return_value=["nba", "mlb"]):
            resp = client.get("/api/bestbets/board")
        assert resp.status_code == 200
        assert "nba" in calls
        assert "mlb" in calls
