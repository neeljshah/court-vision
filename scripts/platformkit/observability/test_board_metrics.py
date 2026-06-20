"""test_board_metrics.py -- per-file tests for observability/board_metrics.py.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/observability/test_board_metrics.py -q

Acceptance (from BE-BOARD-METRICS spec):
  * board of N cards -> metrics dict {n_cards, distinct_prob_ratio, n_dropped_sanitizer, non_discriminating}
  * empty board -> INSUFFICIENT_DATA
  * degenerate MLB-like board (most cards share identical model_prob) -> non_discriminating True
  * pure, no IO, no $ field
  * never raises

ASCII only; <= 300 LOC.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from scripts.platformkit.observability.board_metrics import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_NON_DISCRIMINATING,
    STATUS_OK,
    compute_board_metrics,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_card(
    model_prob: float = 0.55,
    market_prob: float = 0.50,
    matchup: str = "TeamA vs TeamB",
    best_odds: float = 1.90,
    edge_vs_market: float = 0.05,
    market_type: str = "moneyline",
) -> Dict[str, Any]:
    return {
        "model_prob": model_prob,
        "market_prob": market_prob,
        "matchup": matchup,
        "best_odds": best_odds,
        "edge_vs_market": edge_vs_market,
        "market_type": market_type,
    }


def _make_prop_card(
    model_prob: float = 0.60,
    market_prob: float = 0.52,
) -> Dict[str, Any]:
    return {
        "model_prob": model_prob,
        "market_prob": market_prob,
        "matchup": "PlayerX points",
        "best_odds": 1.85,
        "edge_vs_market": 0.08,
        "market_type": "player_prop",
        "stat": "points",
    }


def _degenerate_mlb_board(n: int = 8, shared_prob: float = 0.4655) -> List[Dict[str, Any]]:
    """Mimic MLB fallback board where most cards share the same model_prob."""
    cards = []
    for i in range(n):
        cards.append(_make_card(
            model_prob=shared_prob,  # collapsed fallback prob
            matchup=f"MLB TeamA{i} vs TeamB{i}",
            market_type="moneyline",
        ))
    return cards


# ---------------------------------------------------------------------------
# Core acceptance tests
# ---------------------------------------------------------------------------

class TestEmptyBoard:
    def test_empty_list_returns_insufficient_data(self):
        result = compute_board_metrics([])
        assert result["status"] == STATUS_INSUFFICIENT_DATA

    def test_empty_board_n_cards_zero(self):
        result = compute_board_metrics([])
        assert result["n_cards"] == 0

    def test_empty_board_distinct_prob_ratio_is_none(self):
        result = compute_board_metrics([])
        assert result["distinct_prob_ratio"] is None

    def test_empty_board_non_discriminating_false(self):
        result = compute_board_metrics([])
        # Not discriminating in the failing-sense; insufficient data is not a fabricated edge
        assert result["non_discriminating"] is False


class TestNormalBoard:
    def test_n_cards_matches_post_sanitize_count(self):
        cards = [_make_card(model_prob=0.55 + i * 0.02) for i in range(5)]
        result = compute_board_metrics(cards)
        # No sanitize drops expected (all valid)
        assert result["n_cards"] == 5

    def test_distinct_prob_ratio_all_unique(self):
        cards = [_make_card(model_prob=0.50 + i * 0.05) for i in range(6)]
        result = compute_board_metrics(cards)
        # All distinct -> ratio = 1.0
        assert result["distinct_prob_ratio"] == pytest.approx(1.0, abs=1e-6)

    def test_status_ok_on_clean_varied_board(self):
        cards = [_make_card(model_prob=0.50 + i * 0.05) for i in range(6)]
        result = compute_board_metrics(cards)
        assert result["status"] == STATUS_OK

    def test_non_discriminating_false_on_varied_board(self):
        cards = [_make_card(model_prob=0.50 + i * 0.05) for i in range(6)]
        result = compute_board_metrics(cards)
        assert result["non_discriminating"] is False

    def test_required_keys_present(self):
        cards = [_make_card(model_prob=0.55 + i * 0.03) for i in range(4)]
        result = compute_board_metrics(cards)
        required = {
            "n_cards",
            "distinct_prob_ratio",
            "n_dropped_sanitizer",
            "non_discriminating",
            "prop_share",
            "game_share",
            "status",
            "honest_note",
        }
        assert required.issubset(result.keys()), (
            "Missing keys: %s" % (required - result.keys())
        )

    def test_no_dollar_field(self):
        cards = [_make_card(model_prob=0.55 + i * 0.03) for i in range(4)]
        result = compute_board_metrics(cards)
        banned = {"pnl", "profit", "roi", "bankroll", "usd", "dollar", "stake"}
        for key in result.keys():
            assert key.lower() not in banned, (
                "Banned $ field present: %s" % key
            )


class TestSanitizerDrops:
    def test_yes_vs_no_card_is_dropped(self):
        clean_cards = [_make_card(model_prob=0.55 + i * 0.05) for i in range(3)]
        binary_card = _make_card(matchup="Team A Yes vs No", model_prob=0.51,
                                  market_prob=0.50, best_odds=1.91,
                                  edge_vs_market=0.01)
        all_cards = clean_cards + [binary_card]
        result = compute_board_metrics(all_cards)
        assert result["n_dropped_sanitizer"] >= 1

    def test_degenerate_market_prob_card_dropped(self):
        clean = [_make_card(model_prob=0.55 + i * 0.05) for i in range(3)]
        bad = _make_card(market_prob=0.005)  # below 0.02 threshold
        all_cards = clean + [bad]
        result = compute_board_metrics(all_cards)
        assert result["n_dropped_sanitizer"] >= 1

    def test_extreme_odds_card_dropped(self):
        clean = [_make_card(model_prob=0.55 + i * 0.05) for i in range(3)]
        longshot = _make_card(best_odds=100.0)  # above 50.0 threshold
        all_cards = clean + [longshot]
        result = compute_board_metrics(all_cards)
        assert result["n_dropped_sanitizer"] >= 1

    def test_wide_edge_card_dropped(self):
        clean = [_make_card(model_prob=0.55 + i * 0.05) for i in range(3)]
        corrupt = _make_card(edge_vs_market=0.45)  # above 0.30 threshold
        all_cards = clean + [corrupt]
        result = compute_board_metrics(all_cards)
        assert result["n_dropped_sanitizer"] >= 1

    def test_all_cards_dropped_yields_insufficient_data(self):
        bad_cards = [
            _make_card(matchup="Yes vs No choice", market_prob=0.50),
            _make_card(market_prob=0.001),
        ]
        result = compute_board_metrics(bad_cards)
        assert result["status"] == STATUS_INSUFFICIENT_DATA
        assert result["n_cards"] == 0


class TestDegenerateMLBBoard:
    """Degenerate MLB-like board: most cards share the same model_prob."""

    def test_non_discriminating_true(self):
        cards = _degenerate_mlb_board(n=8, shared_prob=0.4655)
        result = compute_board_metrics(cards)
        assert result["non_discriminating"] is True

    def test_status_non_discriminating(self):
        cards = _degenerate_mlb_board(n=8, shared_prob=0.4655)
        result = compute_board_metrics(cards)
        assert result["status"] == STATUS_NON_DISCRIMINATING

    def test_distinct_prob_ratio_low(self):
        cards = _degenerate_mlb_board(n=8, shared_prob=0.4655)
        result = compute_board_metrics(cards)
        # All share same prob -> ratio = 1/8 = 0.125 (well below 0.5 threshold)
        assert result["distinct_prob_ratio"] is not None
        assert result["distinct_prob_ratio"] < 0.5

    def test_n_cards_populated(self):
        cards = _degenerate_mlb_board(n=8, shared_prob=0.4655)
        result = compute_board_metrics(cards)
        assert result["n_cards"] == 8

    def test_mixed_degenerate_only_most_collapsed(self):
        """6-of-8 cards share the same prob -> still non-discriminating."""
        cards = [_make_card(model_prob=0.4655) for _ in range(6)]
        cards += [_make_card(model_prob=0.60), _make_card(model_prob=0.70)]
        result = compute_board_metrics(cards)
        # 3 distinct probs out of 8 cards = ratio 0.375 < 0.5 -> non_discriminating
        assert result["non_discriminating"] is True


class TestPropVsGameSplit:
    def test_all_game_cards_zero_prop_share(self):
        cards = [_make_card(market_type="moneyline", model_prob=0.50 + i * 0.05)
                 for i in range(4)]
        result = compute_board_metrics(cards)
        assert result["prop_share"] == pytest.approx(0.0, abs=1e-6)
        assert result["game_share"] == pytest.approx(1.0, abs=1e-6)

    def test_all_prop_cards_full_prop_share(self):
        cards = [_make_prop_card(model_prob=0.50 + i * 0.05) for i in range(4)]
        result = compute_board_metrics(cards)
        assert result["prop_share"] == pytest.approx(1.0, abs=1e-6)
        assert result["game_share"] == pytest.approx(0.0, abs=1e-6)

    def test_mixed_board_split(self):
        game_cards = [_make_card(model_prob=0.50 + i * 0.05) for i in range(3)]
        prop_cards = [_make_prop_card(model_prob=0.60 + i * 0.03) for i in range(1)]
        result = compute_board_metrics(game_cards + prop_cards)
        assert result["prop_share"] == pytest.approx(0.25, abs=1e-5)
        assert result["game_share"] == pytest.approx(0.75, abs=1e-5)


class TestNeverRaises:
    """compute_board_metrics must never raise on any input."""

    def test_none_input(self):
        result = compute_board_metrics(None)  # type: ignore
        assert "status" in result

    def test_non_list_input(self):
        result = compute_board_metrics("not a list")  # type: ignore
        assert "status" in result

    def test_cards_with_non_dict_elements(self):
        result = compute_board_metrics(["bad", 42, None, {"model_prob": 0.55,
                                                           "market_prob": 0.50,
                                                           "matchup": "A vs B",
                                                           "best_odds": 1.9,
                                                           "edge_vs_market": 0.05,
                                                           "market_type": "moneyline"}])
        assert "n_cards" in result

    def test_cards_with_missing_fields(self):
        result = compute_board_metrics([{"market_prob": 0.50}, {}, {"model_prob": "bad"}])
        assert "status" in result

    def test_single_valid_card(self):
        result = compute_board_metrics([_make_card()])
        assert result["n_cards"] == 1
        assert result["status"] in (STATUS_OK, STATUS_INSUFFICIENT_DATA)
