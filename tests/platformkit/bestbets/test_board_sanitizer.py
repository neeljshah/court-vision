"""Per-file tests for scripts/platformkit/bestbets/board_sanitizer.py.

QA1-board-sanitizer acceptance criteria:
  * sanitize() drops a card: matchup='Yes vs No', market_prob=0.0015,
    best_odds=666.67, edge_vs_market=0.34.
  * sanitize() keeps a normal NBA moneyline card:
    market_prob=0.52, best_odds=1.9, edge_vs_market=0.04.
  * compute_best_bets still returns status='ok', edge_claimed=False, no $ field
    when sanitize() is wired in as the final filter step.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/bestbets/test_board_sanitizer.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from datetime import datetime, timedelta, timezone

from scripts.platformkit.bestbets.board_sanitizer import (
    DEAD_MARKET_PROB,
    MAX_ABS_EDGE,
    MAX_BEST_ODDS,
    MIN_MARKET_PROB,
    sanitize,
)
from predict_service.bestbets_compute import compute_best_bets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_polymarket_card() -> Dict[str, Any]:
    """A degenerate Polymarket binary event card -- must be dropped."""
    return {
        "game_id": "pm_01",
        "matchup": "Yes vs No",          # non-sports binary
        "sport": "polymarket",
        "market_type": "binary",
        "prop_player": None,
        "prop_stat": None,
        "side": "yes",
        "model_prob": 0.34,
        "market_prob": 0.0015,           # < MIN_MARKET_PROB (0.02)
        "best_book": "polymarket",
        "best_odds": 666.67,             # > MAX_BEST_ODDS (50)
        "all_books": [],
        "edge_vs_market": 0.34,          # > MAX_ABS_EDGE (0.30)
        "units": 1.0,
        "tier": "C",
        "confidence": 0.34,
        "clv": {"clv_pct": None, "beat_close": None,
                "clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True},
        "clv_is_proxy": True,
        "status": "pregame",
        "honest_note": "test",
    }


def _make_nba_card() -> Dict[str, Any]:
    """A healthy NBA moneyline card -- must be kept."""
    return {
        "game_id": "nba_01",
        "matchup": "Lakers vs Celtics",   # real sports matchup
        "sport": "nba",
        "market_type": "moneyline",
        "prop_player": None,
        "prop_stat": None,
        "side": "home",
        "model_prob": 0.55,
        "market_prob": 0.52,             # >= MIN_MARKET_PROB
        "best_book": "draftkings",
        "best_odds": 1.9,                # <= MAX_BEST_ODDS
        "all_books": [],
        "edge_vs_market": 0.04,          # <= MAX_ABS_EDGE
        "units": 1.0,
        "tier": "B",
        "confidence": 0.55,
        "clv": {"clv_pct": None, "beat_close": None,
                "clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True},
        "clv_is_proxy": True,
        "status": "pregame",
        "honest_note": "test",
    }


# ---------------------------------------------------------------------------
# Core acceptance test (acceptance criteria from the task spec)
# ---------------------------------------------------------------------------

class TestSanitizeAcceptanceCriteria:
    """Direct acceptance tests matching the task spec exactly."""

    def test_drops_polymarket_binary_card(self):
        """sanitize() MUST drop the degenerate Polymarket card."""
        card = _make_polymarket_card()
        result = sanitize([card])
        assert result == [], (
            f"Expected empty list; kept: {result}"
        )

    def test_keeps_nba_moneyline_card(self):
        """sanitize() MUST keep the normal NBA moneyline card."""
        card = _make_nba_card()
        result = sanitize([card])
        assert len(result) == 1
        assert result[0]["game_id"] == "nba_01"

    def test_mixed_list_drops_degenerate_keeps_healthy(self):
        """With both cards, only the NBA card survives."""
        bad = _make_polymarket_card()
        good = _make_nba_card()
        result = sanitize([bad, good])
        assert len(result) == 1
        assert result[0]["game_id"] == "nba_01"


# ---------------------------------------------------------------------------
# Individual criterion tests
# ---------------------------------------------------------------------------

class TestSanitizeCriteria:

    def test_yes_vs_no_case_insensitive(self):
        """'yes vs no' detection is case-insensitive."""
        for matchup in ["Yes vs No", "YES VS NO", "yes vs no", "Yes Vs No"]:
            card = dict(_make_nba_card(), matchup=matchup, market_prob=0.5,
                        best_odds=2.0, edge_vs_market=0.03)
            assert sanitize([card]) == [], f"Expected drop for matchup={matchup!r}"

    def test_non_binary_matchup_kept(self):
        """A matchup containing other text is not filtered on matchup alone."""
        card = dict(_make_nba_card(), matchup="Heat vs Nets")
        assert len(sanitize([card])) == 1

    def test_market_prob_below_threshold_dropped(self):
        """Cards with market_prob < MIN_MARKET_PROB (0.02) are dropped."""
        card = dict(_make_nba_card(), market_prob=0.019)
        assert sanitize([card]) == []

    def test_market_prob_at_threshold_kept(self):
        """Cards with market_prob == MIN_MARKET_PROB (0.02) are kept."""
        card = dict(_make_nba_card(), market_prob=MIN_MARKET_PROB)
        assert len(sanitize([card])) == 1

    def test_market_prob_above_threshold_kept(self):
        """Cards with market_prob just above threshold are kept."""
        card = dict(_make_nba_card(), market_prob=0.021)
        assert len(sanitize([card])) == 1

    def test_best_odds_above_ceiling_dropped(self):
        """Cards with best_odds > MAX_BEST_ODDS (50) are dropped."""
        card = dict(_make_nba_card(), best_odds=50.01)
        assert sanitize([card]) == []

    def test_best_odds_at_ceiling_kept(self):
        """Cards with best_odds == MAX_BEST_ODDS (50) are kept."""
        card = dict(_make_nba_card(), best_odds=MAX_BEST_ODDS)
        assert len(sanitize([card])) == 1

    def test_best_odds_none_not_filtered(self):
        """None best_odds does not trigger the odds filter."""
        card = dict(_make_nba_card(), best_odds=None)
        assert len(sanitize([card])) == 1

    def test_edge_vs_market_above_max_dropped(self):
        """Cards with |edge_vs_market| > MAX_ABS_EDGE (0.30) are dropped."""
        card = dict(_make_nba_card(), edge_vs_market=0.31)
        assert sanitize([card]) == []

    def test_edge_vs_market_negative_above_max_dropped(self):
        """Negative edge that exceeds abs threshold is also dropped."""
        card = dict(_make_nba_card(), edge_vs_market=-0.31)
        assert sanitize([card]) == []

    def test_edge_vs_market_at_max_kept(self):
        """Cards with |edge_vs_market| == MAX_ABS_EDGE (0.30) are kept."""
        card = dict(_make_nba_card(), edge_vs_market=MAX_ABS_EDGE)
        assert len(sanitize([card])) == 1

    def test_edge_vs_market_within_range_kept(self):
        """Cards with edge_vs_market within range are kept."""
        card = dict(_make_nba_card(), edge_vs_market=0.04)
        assert len(sanitize([card])) == 1


# ---------------------------------------------------------------------------
# Edge / robustness tests
# ---------------------------------------------------------------------------

class TestSanitizeRobustness:

    def test_empty_list_returns_empty(self):
        assert sanitize([]) == []

    def test_does_not_mutate_input(self):
        """sanitize() returns a new list; the original is unchanged."""
        cards = [_make_nba_card(), _make_polymarket_card()]
        original_len = len(cards)
        _ = sanitize(cards)
        assert len(cards) == original_len  # original list untouched

    def test_unparseable_market_prob_dropped(self):
        """Non-numeric market_prob is treated as degenerate -> drop."""
        card = dict(_make_nba_card(), market_prob="N/A")
        assert sanitize([card]) == []

    def test_all_healthy_cards_pass(self):
        """Three healthy cards all survive."""
        cards = [
            dict(_make_nba_card(), game_id=f"g{i}", market_prob=0.50 + i * 0.01,
                 edge_vs_market=0.03 + i * 0.005)
            for i in range(3)
        ]
        assert len(sanitize(cards)) == 3


# ---------------------------------------------------------------------------
# QA-ISSUE-1: stale / dead-market exclusion (the exact 558934 symptom)
# ---------------------------------------------------------------------------

class TestStaleAndDeadMarket:
    """A card against a resolved/stale market must never show an edge."""

    def _make_stale_polymarket(self) -> Dict[str, Any]:
        """The exact QA symptom: soccer_intl Polymarket 'Yes vs No' binary,
        tipoff nearly a year past, market_prob ~0.0005, served as pregame
        Tier-A with edge_vs_market=0.3416."""
        return dict(
            _make_nba_card(),
            game_id="558934",
            matchup="Yes vs No",
            sport="soccer_intl",
            market_prob=0.0005,
            best_odds=2000.0,
            edge_vs_market=0.3416,
            tier="A",
            status="pregame",
            tipoff_utc="2025-07-02T00:00:00+00:00",
        )

    def test_exact_qa_symptom_card_dropped(self):
        """The 558934 dead/stale card is dropped (any one criterion suffices)."""
        assert sanitize([self._make_stale_polymarket()]) == []

    def test_past_tipoff_alone_drops_otherwise_healthy_card(self):
        """A card healthy on every other axis is dropped purely for a past tipoff."""
        past = (datetime.now(timezone.utc) - timedelta(days=300)).isoformat()
        card = dict(_make_nba_card(), tipoff_utc=past)
        assert sanitize([card]) == []

    def test_future_tipoff_kept(self):
        """A future tipoff does not trigger the stale filter."""
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        card = dict(_make_nba_card(), tipoff_utc=future)
        assert len(sanitize([card])) == 1

    def test_now_is_injectable_for_determinism(self):
        """Injecting now lets a past-tipoff card be evaluated deterministically."""
        card = dict(_make_nba_card(), tipoff_utc="2025-07-02T00:00:00+00:00")
        ref = datetime(2025, 7, 3, tzinfo=timezone.utc)  # after tipoff
        assert sanitize([card], now=ref) == []
        ref_before = datetime(2025, 7, 1, tzinfo=timezone.utc)  # before tipoff
        assert len(sanitize([card], now=ref_before)) == 1

    def test_dead_market_below_floor_dropped(self):
        """market_prob < DEAD_MARKET_PROB (resolved book) is dropped."""
        card = dict(_make_nba_card(), market_prob=DEAD_MARKET_PROB / 2,
                    tipoff_utc=None)
        assert sanitize([card]) == []

    def test_zulu_suffix_tipoff_parsed(self):
        """A trailing 'Z' UTC designator parses and still triggers the filter."""
        card = dict(_make_nba_card(), tipoff_utc="2025-07-02T00:00:00Z")
        ref = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert sanitize([card], now=ref) == []

    def test_missing_tipoff_not_dropped_on_that_alone(self):
        """No tipoff info -> not dropped on the stale criterion alone."""
        card = dict(_make_nba_card(), tipoff_utc=None)
        assert len(sanitize([card])) == 1


# ---------------------------------------------------------------------------
# Integration: compute_best_bets wiring
# ---------------------------------------------------------------------------

class TestComputeBestBetsWiring:
    """sanitize() is the final filter in compute_best_bets; verify end-to-end shape."""

    def _patch_compute(self, cards: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run compute_best_bets with all IO patched, returning the result."""
        with patch("predict_service.bestbets_compute._get_edge_view",
                   return_value={"status": "ok", "games": []}), \
             patch("predict_service.bestbets_compute._cards_from_props",
                   return_value=cards):
            return compute_best_bets("nba")

    def test_status_ok_edge_claimed_false(self):
        """compute_best_bets returns status='ok' and edge_claimed=False."""
        result = self._patch_compute([_make_nba_card()])
        assert result["status"] == "ok"
        assert result["edge_claimed"] is False

    def test_no_dollar_field_in_result(self):
        """No $ / pnl / roi / profit field in the result or any card."""
        result = self._patch_compute([_make_nba_card()])
        forbidden = {"dollar", "pnl", "roi", "profit", "bankroll", "usd"}
        top_keys = {k.lower() for k in result}
        assert not (top_keys & forbidden)
        for card in result.get("cards", []):
            card_keys = {k.lower() for k in card}
            assert not (card_keys & forbidden)

    def test_sanitized_degenerate_card_absent(self):
        """After sanitize(), the degenerate Polymarket card does not appear
        in compute_best_bets output even when _cards_from_props returns it."""
        bad = _make_polymarket_card()
        good = _make_nba_card()
        result = self._patch_compute([bad, good])
        # The bad card must be absent; the good one may or may not pass the
        # edge_vs_market > 0 pre-filter in _cards_from_props, but the bad card
        # is unambiguously gone if sanitize() is wired correctly.
        game_ids = [c["game_id"] for c in result.get("cards", [])]
        assert "pm_01" not in game_ids, (
            "Degenerate Polymarket card leaked through sanitize()"
        )
