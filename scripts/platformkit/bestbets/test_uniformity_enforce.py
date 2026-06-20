"""Per-file tests for uniformity_enforce.py.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/bestbets/test_uniformity_enforce.py -q

Acceptance (from workstream spec be-r2-w4-mlb-uniformity-enforce):

  1. A card list where 11 MLB cards share only 2 distinct model_prob values
     (0.5345 / 0.4655) is returned with ALL MLB cards demoted:
       - tier == 'C'
       - edge_claimed == False
       - flat_prior == True  (flat-prior marker)
       - honest_note mentions "model unavailable -- base rate only"
  2. Genuine discriminating sports on the same board are left untouched.
  3. A healthy varied board (all distinct probs) is returned unchanged.
  4. The function never raises (tested with None, empty list, garbage input).
  5. No $ / roi / pnl field is ever added to a card.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

import pytest

from scripts.platformkit.bestbets.uniformity_enforce import (
    FLAT_PRIOR_NOTE,
    MIN_CARDS_PER_SPORT,
    enforce_uniformity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FORBIDDEN_KEYS = frozenset({
    "pnl", "roi", "bankroll", "profit", "stake", "usd", "dollar",
})


def _has_forbidden_key(obj: Any) -> bool:
    """Recursively scan obj for any key matching FORBIDDEN_KEYS (case-insensitive)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                return True
            if _has_forbidden_key(v):
                return True
    elif isinstance(obj, (list, tuple)):
        return any(_has_forbidden_key(item) for item in obj)
    return False


def _mlb_card(model_prob: float, game_id: str = "g1", **extras) -> Dict[str, Any]:
    """Minimal MLB BestBetCard dict."""
    return {
        "sport": "mlb",
        "game_id": game_id,
        "model_prob": model_prob,
        "edge_claimed": True,
        "tier": "A",
        **extras,
    }


def _nba_card(model_prob: float, game_id: str = "g1", **extras) -> Dict[str, Any]:
    """Minimal NBA BestBetCard dict."""
    return {
        "sport": "nba",
        "game_id": game_id,
        "model_prob": model_prob,
        "edge_claimed": True,
        "tier": "B",
        **extras,
    }


def _build_degenerate_mlb_board() -> List[Dict[str, Any]]:
    """11 MLB cards sharing only 2 distinct model_prob values (the QA iter 1/8 scenario)."""
    probs = [0.5345] * 6 + [0.4655] * 5
    return [_mlb_card(p, game_id=f"game_{i}") for i, p in enumerate(probs)]


def _build_discriminating_mlb_board() -> List[Dict[str, Any]]:
    """6 MLB cards all with distinct model_prob values -> healthy board."""
    probs = [0.51, 0.48, 0.55, 0.43, 0.60, 0.38]
    return [_mlb_card(p, game_id=f"game_{i}") for i, p in enumerate(probs)]


# ---------------------------------------------------------------------------
# 1. Degenerate MLB board -- spec acceptance tests
# ---------------------------------------------------------------------------

class TestDegenerateMlbBoard:
    """QA iter 1/8 P1: 11 MLB cards, 2 distinct model_prob values -> all demoted."""

    def setup_method(self):
        self.cards = _build_degenerate_mlb_board()

    def test_all_mlb_cards_tier_c(self):
        result = enforce_uniformity(self.cards)
        for c in result:
            assert c["tier"] == "C", f"Expected tier C; got {c['tier']} for card {c}"

    def test_all_mlb_cards_edge_claimed_false(self):
        result = enforce_uniformity(self.cards)
        for c in result:
            assert c["edge_claimed"] is False

    def test_all_mlb_cards_have_flat_prior_marker(self):
        result = enforce_uniformity(self.cards)
        for c in result:
            assert c.get("flat_prior") is True

    def test_all_mlb_cards_have_honest_note(self):
        result = enforce_uniformity(self.cards)
        for c in result:
            note = c.get("honest_note", "")
            assert "model unavailable" in note and "base rate" in note, (
                f"honest_note missing key phrases: {note!r}"
            )

    def test_all_mlb_cards_have_degenerate_model_flag(self):
        result = enforce_uniformity(self.cards)
        for c in result:
            assert c.get("degenerate_model") is True

    def test_flat_prior_reason_is_ascii(self):
        result = enforce_uniformity(self.cards)
        for c in result:
            reason = c.get("flat_prior_reason", "")
            reason.encode("ascii")  # raises if non-ASCII

    def test_returns_same_list_object(self):
        """enforce_uniformity returns the same list (in-place semantics)."""
        result = enforce_uniformity(self.cards)
        assert result is self.cards

    def test_no_forbidden_keys_added(self):
        result = enforce_uniformity(self.cards)
        for c in result:
            assert not _has_forbidden_key(c), f"Forbidden key found in card: {c}"


# ---------------------------------------------------------------------------
# 2. Mixed board -- degenerate MLB + discriminating NBA untouched
# ---------------------------------------------------------------------------

class TestMixedBoard:
    """Degenerate MLB cards are demoted; genuine discriminating NBA cards are not."""

    def setup_method(self):
        self.mlb_cards = _build_degenerate_mlb_board()  # 11 MLB, 2 distinct probs
        # 5 NBA cards with distinct probs spanning 0.42..0.62
        self.nba_cards = [
            _nba_card(round(0.42 + i * 0.05, 6), game_id=f"nba_{i}")
            for i in range(5)
        ]
        self.board = self.mlb_cards + self.nba_cards
        # Snapshot original NBA state before enforcement
        self.nba_snapshot = copy.deepcopy(self.nba_cards)

    def test_mlb_demoted(self):
        result = enforce_uniformity(self.board)
        mlb_result = [c for c in result if c["sport"] == "mlb"]
        assert all(c["edge_claimed"] is False for c in mlb_result)
        assert all(c["tier"] == "C" for c in mlb_result)
        assert all(c.get("flat_prior") is True for c in mlb_result)

    def test_nba_untouched(self):
        """NBA cards must not be modified when their probs are discriminating."""
        result = enforce_uniformity(self.board)
        nba_result = [c for c in result if c["sport"] == "nba"]
        # Compare to snapshot (deep copy taken before enforcement)
        assert nba_result == self.nba_snapshot, (
            "NBA cards were modified even though their probs are discriminating."
        )

    def test_nba_tier_unchanged(self):
        result = enforce_uniformity(self.board)
        nba_result = [c for c in result if c["sport"] == "nba"]
        assert all(c["tier"] == "B" for c in nba_result)

    def test_nba_edge_claimed_unchanged(self):
        result = enforce_uniformity(self.board)
        nba_result = [c for c in result if c["sport"] == "nba"]
        assert all(c["edge_claimed"] is True for c in nba_result)


# ---------------------------------------------------------------------------
# 3. Healthy varied board -- untouched
# ---------------------------------------------------------------------------

class TestHealthyBoard:
    """A board where all cards have distinct probs is returned entirely unchanged."""

    def setup_method(self):
        self.cards = _build_discriminating_mlb_board()
        self.snapshot = copy.deepcopy(self.cards)

    def test_healthy_board_untouched(self):
        result = enforce_uniformity(self.cards)
        assert result == self.snapshot, (
            "Healthy board was modified when all cards have distinct probs."
        )

    def test_tier_preserved(self):
        result = enforce_uniformity(self.cards)
        for c in result:
            assert c["tier"] == "A"

    def test_edge_claimed_preserved(self):
        result = enforce_uniformity(self.cards)
        for c in result:
            assert c["edge_claimed"] is True

    def test_no_flat_prior_key_added(self):
        result = enforce_uniformity(self.cards)
        for c in result:
            assert "flat_prior" not in c


# ---------------------------------------------------------------------------
# 4. Small slate below MIN_CARDS_PER_SPORT -- left untouched
# ---------------------------------------------------------------------------

class TestSmallSlate:
    """A 2-card slate sharing one prob is too small to verdict -> left untouched."""

    def test_two_cards_same_prob_untouched(self):
        cards = [_mlb_card(0.5345, game_id=f"g{i}") for i in range(2)]
        snapshot = copy.deepcopy(cards)
        result = enforce_uniformity(cards)
        assert result == snapshot

    def test_min_cards_boundary_untouched(self):
        """Exactly MIN_CARDS_PER_SPORT - 1 cards -> untouched."""
        n = MIN_CARDS_PER_SPORT - 1
        cards = [_mlb_card(0.5345, game_id=f"g{i}") for i in range(n)]
        snapshot = copy.deepcopy(cards)
        result = enforce_uniformity(cards)
        assert result == snapshot


# ---------------------------------------------------------------------------
# 5. Robustness -- never raises
# ---------------------------------------------------------------------------

class TestRobustness:

    def test_never_raises_on_none(self):
        """None input must not raise."""
        result = enforce_uniformity(None)  # type: ignore[arg-type]
        assert result is None or isinstance(result, list)

    def test_never_raises_on_empty_list(self):
        result = enforce_uniformity([])
        assert result == []

    def test_never_raises_on_garbage_elements(self):
        """Mixed list with non-dict entries must not raise."""
        cards = [None, 42, "bad", _mlb_card(0.5345)]
        result = enforce_uniformity(cards)
        assert isinstance(result, list)

    def test_cards_missing_model_prob_skipped(self):
        """Cards without model_prob must not cause errors."""
        cards = [
            {"sport": "mlb", "game_id": f"g{i}", "edge_claimed": True, "tier": "A"}
            for i in range(5)
        ]
        snapshot = copy.deepcopy(cards)
        result = enforce_uniformity(cards)
        # No model_prob -> uniformity guard sees INSUFFICIENT_DATA -> no demotion
        assert result == snapshot

    def test_cards_with_invalid_model_prob_graceful(self):
        """Cards with None/NaN/string model_prob must not raise."""
        cards = [
            {"sport": "mlb", "game_id": "g1", "model_prob": None, "edge_claimed": True, "tier": "A"},
            {"sport": "mlb", "game_id": "g2", "model_prob": "bad", "edge_claimed": True, "tier": "A"},
            {"sport": "mlb", "game_id": "g3", "model_prob": float("nan"), "edge_claimed": True, "tier": "A"},
        ]
        result = enforce_uniformity(cards)
        assert isinstance(result, list)

    def test_no_forbidden_keys_on_healthy_board(self):
        cards = _build_discriminating_mlb_board()
        result = enforce_uniformity(cards)
        for c in result:
            assert not _has_forbidden_key(c)

    def test_no_forbidden_keys_on_demoted_board(self):
        cards = _build_degenerate_mlb_board()
        result = enforce_uniformity(cards)
        for c in result:
            assert not _has_forbidden_key(c)

    def test_honest_note_is_ascii(self):
        """FLAT_PRIOR_NOTE constant must be ASCII-clean."""
        FLAT_PRIOR_NOTE.encode("ascii")

    def test_demoted_cards_have_no_dollar_field(self):
        """Demotion must never add a dollar / P&L field."""
        cards = _build_degenerate_mlb_board()
        result = enforce_uniformity(cards)
        for c in result:
            for key in c:
                assert key.lower() not in FORBIDDEN_KEYS, f"Forbidden key {key!r} found in card"
