"""Per-file tests for predict_service/mlb_board_uniformity_label.py.

BE-F-mlb-uniformity-board-wire (QA iter 1/8 P1).

Acceptance criteria:
  (1) 11 MLB moneyline cards with only 2 distinct model_prob values
      (0.5345 / 0.4655 -- the exact QA symptom) ->
        * honest_note contains 'model unavailable -- base rate only'
        * edge_claimed is False
        * tier is demoted to 'C'
        * degenerate_model is True
  (2) 11 MLB moneyline cards with diverse model_probs -> unchanged
  (3) Non-MLB cards (NBA, tennis, soccer) in the same board -> never touched
  (4) Non-moneyline MLB cards (e.g. market_type='player_prop') -> never touched
  (5) Empty list -> [] (no error)
  (6) Never raises on malformed input
  (7) No $/roi/pnl/profit/bankroll/usd/dollar key introduced by the labeller
  (8) All output strings are pure ASCII

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/test_mlb_board_uniformity_label.py -q
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

import pytest

from predict_service.mlb_board_uniformity_label import (
    UNIFORMITY_NOTE,
    label_mlb_moneyline_cards,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FORBIDDEN_KEYS = frozenset({
    "pnl", "roi", "bankroll", "profit", "stake", "usd", "dollar",
})


def _has_forbidden_key(obj: Any) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                return True
            if _has_forbidden_key(v):
                return True
    elif isinstance(obj, (list, tuple)):
        return any(_has_forbidden_key(item) for item in obj)
    return False


def _mlb_ml_card(
    prob: float,
    gid: str = "mlb_g1",
    tier: str = "A",
    market_type: str = "moneyline",
) -> Dict[str, Any]:
    return {
        "game_id": gid,
        "matchup": "Team A vs Team B",
        "sport": "mlb",
        "market_type": market_type,
        "side": "home",
        "model_prob": prob,
        "market_prob": round(prob - 0.02, 6),
        "edge_vs_market": 0.02,
        "units": 1.0,
        "tier": tier,
        "confidence": prob,
        "status": "pregame",
        "honest_note": "original note",
        "edge_claimed": True,
    }


def _nba_card(prob: float, gid: str = "nba_g1", tier: str = "A") -> Dict[str, Any]:
    return {
        "game_id": gid,
        "matchup": "LAL vs GSW",
        "sport": "nba",
        "market_type": "moneyline",
        "side": "home",
        "model_prob": prob,
        "market_prob": round(prob - 0.02, 6),
        "edge_vs_market": 0.02,
        "units": 1.0,
        "tier": tier,
        "confidence": prob,
        "status": "pregame",
        "honest_note": "original note",
        "edge_claimed": True,
    }


def _flat_mlb_slate(n: int = 11) -> List[Dict[str, Any]]:
    """QA symptom: n MLB cards alternating between exactly 2 model_prob values."""
    cards = []
    for i in range(n):
        prob = 0.5345 if i % 2 == 0 else 0.4655
        cards.append(_mlb_ml_card(prob, gid=f"mlb_{i}"))
    return cards


def _diverse_mlb_slate(n: int = 11) -> List[Dict[str, Any]]:
    """Healthy MLB slate: n cards each with a distinct model_prob."""
    cards = []
    for i in range(n):
        prob = round(0.45 + i * 0.009, 6)
        cards.append(_mlb_ml_card(prob, gid=f"mlb_div_{i}"))
    return cards


# ---------------------------------------------------------------------------
# (1) 11 MLB cards with 2 distinct probs -> demoted
# ---------------------------------------------------------------------------

class TestFlatMlbSlateDemoted:

    def test_honest_note_contains_model_unavailable(self):
        """All MLB cards get the 'model unavailable -- base rate only' label."""
        cards = _flat_mlb_slate(11)
        result = label_mlb_moneyline_cards(cards)
        for c in result:
            assert "model unavailable" in c["honest_note"].lower(), (
                f"Expected 'model unavailable' in honest_note, got: {c['honest_note']!r}"
            )
            assert "base rate only" in c["honest_note"].lower()

    def test_edge_claimed_false_after_label(self):
        """edge_claimed must be False on every demoted card."""
        cards = _flat_mlb_slate(11)
        label_mlb_moneyline_cards(cards)
        assert all(c["edge_claimed"] is False for c in cards)

    def test_tier_demoted_to_c(self):
        """Tier must be 'C' (never A or B) for a degenerate MLB card."""
        cards = _flat_mlb_slate(11)
        label_mlb_moneyline_cards(cards)
        assert all(c["tier"] == "C" for c in cards)

    def test_degenerate_model_flag_set(self):
        """degenerate_model must be True (machine-readable flag) on every card."""
        cards = _flat_mlb_slate(11)
        label_mlb_moneyline_cards(cards)
        assert all(c.get("degenerate_model") is True for c in cards)

    def test_uniformity_note_constant_matches_module_constant(self):
        """The exact UNIFORMITY_NOTE string is written to each card."""
        cards = _flat_mlb_slate(11)
        label_mlb_moneyline_cards(cards)
        assert all(c["honest_note"] == UNIFORMITY_NOTE for c in cards)

    def test_single_value_collapse_also_demoted(self):
        """All 11 cards sharing ONE prob value is an even stronger collapse signal."""
        cards = [_mlb_ml_card(0.5000, gid=f"mlb_{i}") for i in range(11)]
        label_mlb_moneyline_cards(cards)
        assert all(c["tier"] == "C" for c in cards)
        assert all(c["edge_claimed"] is False for c in cards)

    def test_original_tier_a_and_b_both_demoted(self):
        """Both Tier-A and Tier-B MLB moneyline cards get demoted."""
        flat_a = [_mlb_ml_card(0.5345, gid=f"a_{i}", tier="A") for i in range(6)]
        flat_b = [_mlb_ml_card(0.4655, gid=f"b_{i}", tier="B") for i in range(5)]
        cards = flat_a + flat_b
        label_mlb_moneyline_cards(cards)
        assert all(c["tier"] == "C" for c in cards)

    def test_no_forbidden_dollar_keys_introduced(self):
        """Labeller never introduces $/roi/pnl/profit keys."""
        cards = _flat_mlb_slate(11)
        label_mlb_moneyline_cards(cards)
        assert not _has_forbidden_key(cards)

    def test_all_strings_are_ascii(self):
        """Every string value on labelled cards must be pure ASCII."""
        cards = _flat_mlb_slate(11)
        label_mlb_moneyline_cards(cards)
        for c in cards:
            for v in c.values():
                if isinstance(v, str):
                    v.encode("ascii")  # raises UnicodeEncodeError if not ASCII


# ---------------------------------------------------------------------------
# (2) 11 MLB cards with diverse probs -> unchanged
# ---------------------------------------------------------------------------

class TestDiverseMlbSlateUntouched:

    def test_diverse_slate_not_demoted(self):
        """11 MLB cards with distinct probs must be left untouched."""
        cards = _diverse_mlb_slate(11)
        original = copy.deepcopy(cards)
        label_mlb_moneyline_cards(cards)
        # tier and edge_claimed must be unchanged
        for before, after in zip(original, cards):
            assert after["tier"] == before["tier"]
            assert after["edge_claimed"] == before["edge_claimed"]
            assert after["honest_note"] == before["honest_note"]

    def test_diverse_slate_no_degenerate_model_flag(self):
        """degenerate_model must NOT appear on a healthy diverse slate."""
        cards = _diverse_mlb_slate(11)
        label_mlb_moneyline_cards(cards)
        assert all("degenerate_model" not in c for c in cards)


# ---------------------------------------------------------------------------
# (3) Non-MLB cards in the same board -> never touched
# ---------------------------------------------------------------------------

class TestNonMlbCardsUntouched:

    def test_nba_cards_not_touched_when_mlb_flat(self):
        """NBA cards must be untouched even when MLB moneyline is degenerate."""
        nba_cards = [_nba_card(0.6 + i * 0.01, gid=f"nba_{i}") for i in range(5)]
        nba_orig = copy.deepcopy(nba_cards)

        mlb_cards = _flat_mlb_slate(11)
        board = nba_cards + mlb_cards

        label_mlb_moneyline_cards(board)

        for orig, after in zip(nba_orig, nba_cards):
            assert after["tier"] == orig["tier"]
            assert after["honest_note"] == orig["honest_note"]
            assert after.get("edge_claimed") == orig.get("edge_claimed")
            assert "degenerate_model" not in after

    def test_tennis_soccer_cards_not_touched(self):
        """Other sports are never relabelled."""
        def _other_card(sport: str, i: int) -> Dict[str, Any]:
            return {
                "game_id": f"{sport}_{i}", "sport": sport,
                "market_type": "moneyline", "model_prob": 0.55 + i * 0.01,
                "tier": "A", "edge_claimed": True, "honest_note": "orig",
            }

        others = (
            [_other_card("tennis", i) for i in range(4)]
            + [_other_card("soccer", i) for i in range(4)]
        )
        orig = copy.deepcopy(others)
        board = others + _flat_mlb_slate(11)
        label_mlb_moneyline_cards(board)

        for before, after in zip(orig, others):
            assert after["tier"] == before["tier"]
            assert "degenerate_model" not in after


# ---------------------------------------------------------------------------
# (4) Non-moneyline MLB cards -> never touched
# ---------------------------------------------------------------------------

class TestNonMoneylineMlbUntouched:

    def test_mlb_player_prop_cards_not_touched(self):
        """MLB player_prop cards must be left untouched even on a flat moneyline slate."""
        prop_cards = [
            _mlb_ml_card(0.5345, gid=f"pp_{i}", market_type="player_prop")
            for i in range(5)
        ]
        prop_orig = copy.deepcopy(prop_cards)

        board = _flat_mlb_slate(11) + prop_cards
        label_mlb_moneyline_cards(board)

        for before, after in zip(prop_orig, prop_cards):
            assert after["tier"] == before["tier"]
            assert after["honest_note"] == before["honest_note"]
            assert "degenerate_model" not in after

    def test_mixed_market_types_only_moneyline_affected(self):
        """Only the moneyline slice is inspected and potentially demoted."""
        totals_cards = [
            _mlb_ml_card(0.52, gid=f"tot_{i}", market_type="totals")
            for i in range(4)
        ]
        tot_orig = copy.deepcopy(totals_cards)

        board = _flat_mlb_slate(11) + totals_cards
        label_mlb_moneyline_cards(board)

        for before, after in zip(tot_orig, totals_cards):
            assert after["tier"] == before["tier"]
            assert "degenerate_model" not in after


# ---------------------------------------------------------------------------
# (5) Empty list
# ---------------------------------------------------------------------------

class TestEmptyInput:

    def test_empty_list_returns_empty(self):
        result = label_mlb_moneyline_cards([])
        assert result == []

    def test_empty_list_does_not_raise(self):
        label_mlb_moneyline_cards([])


# ---------------------------------------------------------------------------
# (6) Never raises on malformed input
# ---------------------------------------------------------------------------

class TestRobustness:

    def test_none_input_does_not_raise(self):
        result = label_mlb_moneyline_cards(None)  # type: ignore[arg-type]
        # Should return None or [] without raising
        assert result is None or result == []

    def test_non_list_input_does_not_raise(self):
        label_mlb_moneyline_cards("bad")  # type: ignore[arg-type]

    def test_cards_with_missing_model_prob_do_not_raise(self):
        cards = [{"sport": "mlb", "market_type": "moneyline"}] * 11
        label_mlb_moneyline_cards(cards)

    def test_cards_with_invalid_model_prob_skipped_gracefully(self):
        """Cards with None/str/NaN model_prob must not crash the labeller."""
        bad_prob_cards = [
            {"sport": "mlb", "market_type": "moneyline",
             "model_prob": None, "game_id": f"g{i}"}
            for i in range(11)
        ]
        label_mlb_moneyline_cards(bad_prob_cards)  # must not raise

    def test_non_dict_entries_in_list_ignored(self):
        """Non-dict list items are silently skipped."""
        board = [None, 42, "garbage"] + _flat_mlb_slate(11)
        # Must not raise; MLB cards should still be labelled
        result = label_mlb_moneyline_cards(board)
        mlb_cards = [c for c in result if isinstance(c, dict) and c.get("sport") == "mlb"]
        assert all(c["tier"] == "C" for c in mlb_cards)

    def test_large_flat_slate(self):
        """50-card flat slate must be handled without error."""
        cards = _flat_mlb_slate(50)
        label_mlb_moneyline_cards(cards)
        assert all(c["tier"] == "C" for c in cards)


# ---------------------------------------------------------------------------
# (7) No $/roi/pnl/profit key ever introduced
# ---------------------------------------------------------------------------

class TestNoForbiddenKeys:

    def test_degenerate_board_no_dollar_keys(self):
        cards = _flat_mlb_slate(11)
        label_mlb_moneyline_cards(cards)
        assert not _has_forbidden_key(cards)

    def test_diverse_board_no_dollar_keys(self):
        cards = _diverse_mlb_slate(11)
        label_mlb_moneyline_cards(cards)
        assert not _has_forbidden_key(cards)

    def test_mixed_board_no_dollar_keys(self):
        board = _flat_mlb_slate(11) + [_nba_card(0.6 + i * 0.01) for i in range(5)]
        label_mlb_moneyline_cards(board)
        assert not _has_forbidden_key(board)


# ---------------------------------------------------------------------------
# (8) All output strings are pure ASCII
# ---------------------------------------------------------------------------

class TestAsciiOnly:

    def test_uniformity_note_constant_is_ascii(self):
        UNIFORMITY_NOTE.encode("ascii")

    def test_relabelled_cards_strings_are_ascii(self):
        cards = _flat_mlb_slate(11)
        label_mlb_moneyline_cards(cards)
        for c in cards:
            for v in c.values():
                if isinstance(v, str):
                    v.encode("ascii")
