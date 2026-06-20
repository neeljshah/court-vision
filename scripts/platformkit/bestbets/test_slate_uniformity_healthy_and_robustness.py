"""Per-file tests for slate_uniformity_label.py -- healthy board + robustness (BE-R5-2).

Covers:
  1. Well-spread board (8 cards, 8 distinct probs) -> STATUS_OK, cards untouched
  2. Small slate (<3 cards) -> INSUFFICIENT_DATA, no label applied
  3. Robustness -- never raises on None / empty list / garbage input

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/bestbets/test_slate_uniformity_healthy_and_robustness.py -q
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

from scripts.platformkit.bestbets.slate_uniformity_label import (
    MIN_SLATE_CARDS,
    STATUS_INSUFFICIENT_DATA,
    STATUS_OK,
    label_slate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FORBIDDEN_KEYS = frozenset({"pnl", "roi", "bankroll", "profit", "stake", "usd", "dollar"})


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


def _mlb_card(model_prob: float, game_id: str = "g1", **extras) -> Dict[str, Any]:
    return {"sport": "mlb", "game_id": game_id, "model_prob": model_prob, **extras}


def _make_uniform_mlb(n: int = 7, prob: float = 0.4655) -> List[Dict[str, Any]]:
    return [_mlb_card(prob, game_id=f"game_{i}") for i in range(n)]


def _make_spread_mlb(n: int = 8) -> List[Dict[str, Any]]:
    probs = [round(0.40 + i * 0.02, 6) for i in range(n)]
    return [_mlb_card(p, game_id=f"game_{i}") for i, p in enumerate(probs)]


# ---------------------------------------------------------------------------
# 1. Well-spread board (8 cards, 8 distinct probs) -> OK, untouched
# ---------------------------------------------------------------------------

class TestWellSpreadBoard:
    """8 MLB cards each with a unique model_prob -> STATUS_OK, no label added."""

    def setup_method(self):
        self.cards = _make_spread_mlb(n=8)
        self.snapshot = copy.deepcopy(self.cards)

    def test_status_ok(self):
        result = label_slate(self.cards)
        assert result["status"] == STATUS_OK

    def test_model_unavailable_false_top_level(self):
        result = label_slate(self.cards)
        assert result["model_unavailable"] is False

    def test_all_cards_model_unavailable_false(self):
        label_slate(self.cards)
        for c in self.cards:
            assert c.get("model_unavailable") is False

    def test_no_honest_label_added(self):
        label_slate(self.cards)
        for c in self.cards:
            assert "honest_label" not in c, (
                "honest_label must not be added to a healthy board card"
            )

    def test_original_fields_unchanged(self):
        """All pre-existing card fields (sport, game_id, model_prob) must be intact."""
        label_slate(self.cards)
        for orig, cur in zip(self.snapshot, self.cards):
            for key in ("sport", "game_id", "model_prob"):
                assert cur[key] == orig[key], f"Field {key!r} was modified on a healthy card"

    def test_no_edge_vs_market_added(self):
        label_slate(self.cards)
        for c in self.cards:
            assert "edge_vs_market" not in c

    def test_no_forbidden_keys(self):
        label_slate(self.cards)
        for c in self.cards:
            assert not _has_forbidden_key(c)

    def test_n_distinct_reported(self):
        result = label_slate(self.cards)
        assert result["n_distinct"] == 8


# ---------------------------------------------------------------------------
# 2. Small slate (<3 cards) -> INSUFFICIENT_DATA, no label applied
# ---------------------------------------------------------------------------

class TestSmallSlate:
    """Slates with fewer than MIN_SLATE_CARDS cards get INSUFFICIENT_DATA -- no label."""

    def test_single_card_insufficient(self):
        cards = [_mlb_card(0.4655, game_id="g0")]
        snapshot = copy.deepcopy(cards)
        result = label_slate(cards)
        assert result["status"] == STATUS_INSUFFICIENT_DATA
        # Cards must be unchanged.
        assert cards == snapshot

    def test_two_cards_same_prob_insufficient(self):
        cards = [_mlb_card(0.4655, game_id=f"g{i}") for i in range(2)]
        snapshot = copy.deepcopy(cards)
        result = label_slate(cards)
        assert result["status"] == STATUS_INSUFFICIENT_DATA
        assert cards == snapshot, "Small slate cards were mutated unexpectedly"

    def test_boundary_min_minus_one_insufficient(self):
        n = MIN_SLATE_CARDS - 1
        cards = [_mlb_card(0.5000, game_id=f"g{i}") for i in range(n)]
        snapshot = copy.deepcopy(cards)
        result = label_slate(cards)
        assert result["status"] == STATUS_INSUFFICIENT_DATA
        assert cards == snapshot

    def test_model_unavailable_false_on_insufficient(self):
        cards = [_mlb_card(0.5000, game_id="g0")]
        result = label_slate(cards)
        assert result["model_unavailable"] is False

    def test_no_label_on_small_cards(self):
        cards = [_mlb_card(0.4655, game_id=f"g{i}") for i in range(2)]
        label_slate(cards)
        for c in cards:
            assert "model_unavailable" not in c
            assert "honest_label" not in c


# ---------------------------------------------------------------------------
# 3. Robustness -- never raises
# ---------------------------------------------------------------------------

class TestRobustness:

    def test_never_raises_on_none(self):
        result = label_slate(None)  # type: ignore[arg-type]
        assert isinstance(result, dict)

    def test_never_raises_on_empty_list(self):
        result = label_slate([])
        assert result["status"] == STATUS_INSUFFICIENT_DATA
        assert result["model_unavailable"] is False

    def test_never_raises_on_garbage_elements(self):
        cards = [None, 42, "bad", _mlb_card(0.4655)]
        result = label_slate(cards)
        assert isinstance(result, dict)

    def test_cards_missing_model_prob_not_counted(self):
        """Cards without model_prob are excluded from the valid-prob count."""
        # 4 MLB cards without model_prob -> n_valid=0 -> INSUFFICIENT_DATA
        cards = [{"sport": "mlb", "game_id": f"g{i}"} for i in range(4)]
        snapshot = copy.deepcopy(cards)
        result = label_slate(cards)
        assert result["status"] == STATUS_INSUFFICIENT_DATA
        assert cards == snapshot

    def test_invalid_model_prob_graceful(self):
        cards = [
            {"sport": "mlb", "game_id": "g1", "model_prob": None},
            {"sport": "mlb", "game_id": "g2", "model_prob": "bad"},
            {"sport": "mlb", "game_id": "g3", "model_prob": float("nan")},
            {"sport": "mlb", "game_id": "g4", "model_prob": 0.4655},
        ]
        result = label_slate(cards)
        # Only 1 valid prob -> INSUFFICIENT_DATA
        assert result["status"] == STATUS_INSUFFICIENT_DATA
        assert isinstance(result, dict)

    def test_result_always_contains_required_keys(self):
        for cards in [None, [], _make_uniform_mlb(3), _make_spread_mlb(8)]:
            result = label_slate(cards)  # type: ignore[arg-type]
            for key in ("status", "model_unavailable", "n_cards", "n_distinct", "reason", "cards"):
                assert key in result, f"Key {key!r} missing from result"

    def test_reason_always_ascii(self):
        for cards in [[], _make_uniform_mlb(5), _make_spread_mlb(6)]:
            result = label_slate(cards)
            result["reason"].encode("ascii")  # raises if non-ASCII

    def test_three_distinct_probs_is_ok(self):
        """3 distinct probs on a 5-card slate is above the 2-distinct trigger -> OK."""
        probs = [0.48, 0.48, 0.52, 0.52, 0.55]
        cards = [_mlb_card(p, game_id=f"g{i}") for i, p in enumerate(probs)]
        result = label_slate(cards)
        # 3 distinct > MAX_DISTINCT_TRIGGER (2) -> status OK
        assert result["status"] == STATUS_OK
        for c in cards:
            assert c.get("model_unavailable") is False
