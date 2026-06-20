"""Per-file tests for slate_uniformity_label.py -- collapse scenarios (BE-R5-2).

Covers:
  1. Single-prob collapse (7 cards, 1 distinct value) -> CONSTANT_FALLBACK
  2. Two-distinct-prob collapse (iter1/8 pattern) -> CONSTANT_FALLBACK
  3. Mixed board: collapsed MLB + healthy NBA -- NBA cards must stay untouched
  4. No fabricated $ / edge_vs_market in any collapse scenario

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/bestbets/test_slate_uniformity_collapse.py -q
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

import pytest

from scripts.platformkit.bestbets.slate_uniformity_label import (
    MAX_DISTINCT_TRIGGER,
    MODEL_UNAVAILABLE_LABEL,
    STATUS_CONSTANT_FALLBACK,
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


def _nba_card(model_prob: float, game_id: str = "g1", **extras) -> Dict[str, Any]:
    return {"sport": "nba", "game_id": game_id, "model_prob": model_prob, **extras}


def _make_uniform_mlb(n: int = 7, prob: float = 0.4655) -> List[Dict[str, Any]]:
    return [_mlb_card(prob, game_id=f"game_{i}") for i in range(n)]


def _make_spread_mlb(n: int = 8) -> List[Dict[str, Any]]:
    probs = [round(0.40 + i * 0.02, 6) for i in range(n)]
    return [_mlb_card(p, game_id=f"game_{i}") for i, p in enumerate(probs)]


# ---------------------------------------------------------------------------
# 1. Single-prob collapse (7 cards, 1 distinct value)
# ---------------------------------------------------------------------------

class TestConstantFallbackSingleProb:
    """7 MLB cards sharing model_prob=0.4655 -> CONSTANT_FALLBACK on every card."""

    def setup_method(self):
        self.cards = _make_uniform_mlb(n=7, prob=0.4655)

    def test_status_constant_fallback(self):
        result = label_slate(self.cards)
        assert result["status"] == STATUS_CONSTANT_FALLBACK

    def test_model_unavailable_true_at_top_level(self):
        result = label_slate(self.cards)
        assert result["model_unavailable"] is True

    def test_every_card_model_unavailable_true(self):
        label_slate(self.cards)
        for c in self.cards:
            assert c.get("model_unavailable") is True, (
                f"Card {c['game_id']} missing model_unavailable=True"
            )

    def test_every_card_has_honest_label(self):
        label_slate(self.cards)
        for c in self.cards:
            label = c.get("honest_label", "")
            assert "model unavailable" in label, (
                f"honest_label missing 'model unavailable': {label!r}"
            )
            assert "base rate" in label, (
                f"honest_label missing 'base rate': {label!r}"
            )

    def test_honest_label_is_ascii(self):
        label_slate(self.cards)
        for c in self.cards:
            c.get("honest_label", "").encode("ascii")

    def test_no_edge_vs_market_fabricated(self):
        label_slate(self.cards)
        for c in self.cards:
            assert "edge_vs_market" not in c, (
                "edge_vs_market must NOT be added to a model_unavailable card"
            )

    def test_no_forbidden_keys_added(self):
        label_slate(self.cards)
        for c in self.cards:
            assert not _has_forbidden_key(c), f"Forbidden key in card: {c}"

    def test_returns_same_list_object(self):
        result = label_slate(self.cards)
        assert result["cards"] is self.cards

    def test_model_prob_preserved(self):
        """Original model_prob must not be modified by the labeller."""
        label_slate(self.cards)
        for c in self.cards:
            assert c["model_prob"] == pytest.approx(0.4655)

    def test_reason_is_ascii(self):
        result = label_slate(self.cards)
        result["reason"].encode("ascii")


# ---------------------------------------------------------------------------
# 2. Two-distinct-prob collapse (iter1/8 pattern: 0.5345 / 0.4655)
# ---------------------------------------------------------------------------

class TestConstantFallbackTwoDistinct:
    """11 cards with 2 distinct probs -> CONSTANT_FALLBACK (<=2 triggers label)."""

    def setup_method(self):
        probs = [0.5345] * 6 + [0.4655] * 5
        self.cards = [_mlb_card(p, game_id=f"g{i}") for i, p in enumerate(probs)]

    def test_status_constant_fallback(self):
        result = label_slate(self.cards)
        assert result["status"] == STATUS_CONSTANT_FALLBACK

    def test_all_cards_labelled(self):
        label_slate(self.cards)
        for c in self.cards:
            assert c.get("model_unavailable") is True

    def test_n_distinct_reported(self):
        result = label_slate(self.cards)
        # 2 distinct probs across all 11 cards
        assert result["n_distinct"] == 2


# ---------------------------------------------------------------------------
# 3. Mixed board: collapsed MLB + healthy NBA
# ---------------------------------------------------------------------------

class TestMixedBoard:
    """MLB collapses; NBA cards with spread probs must remain untouched."""

    def setup_method(self):
        # 7 MLB cards all with the same prob -> CONSTANT_FALLBACK for MLB
        self.mlb_cards = _make_uniform_mlb(n=7, prob=0.4655)
        # 5 NBA cards with 5 distinct probs -> healthy
        nba_probs = [round(0.48 + i * 0.04, 6) for i in range(5)]
        self.nba_cards = [_nba_card(p, game_id=f"nba_{i}") for i, p in enumerate(nba_probs)]
        self.board = self.mlb_cards + self.nba_cards
        self.nba_snapshot = copy.deepcopy(self.nba_cards)

    def test_overall_status_constant_fallback(self):
        result = label_slate(self.board)
        assert result["status"] == STATUS_CONSTANT_FALLBACK

    def test_mlb_cards_labelled_unavailable(self):
        label_slate(self.board)
        for c in self.mlb_cards:
            assert c.get("model_unavailable") is True

    def test_nba_cards_model_unavailable_false(self):
        label_slate(self.board)
        for c in self.nba_cards:
            assert c.get("model_unavailable") is False

    def test_nba_cards_no_honest_label(self):
        label_slate(self.board)
        for c in self.nba_cards:
            assert "honest_label" not in c, (
                "NBA card received honest_label despite being a healthy slate"
            )

    def test_nba_original_fields_intact(self):
        label_slate(self.board)
        for orig, cur in zip(self.nba_snapshot, self.nba_cards):
            for key in ("sport", "game_id", "model_prob"):
                assert cur[key] == orig[key]

    def test_mlb_no_edge_vs_market(self):
        label_slate(self.board)
        for c in self.mlb_cards:
            assert "edge_vs_market" not in c


# ---------------------------------------------------------------------------
# 4. No fabricated $ / edge_vs_market in any collapse scenario
# ---------------------------------------------------------------------------

class TestNoFabricatedField:

    def test_single_prob_slate_no_dollar_key(self):
        cards = _make_uniform_mlb(n=5, prob=0.4655)
        label_slate(cards)
        for c in cards:
            assert not _has_forbidden_key(c)
            assert "edge_vs_market" not in c

    def test_healthy_slate_no_dollar_key(self):
        cards = _make_spread_mlb(n=6)
        label_slate(cards)
        for c in cards:
            assert not _has_forbidden_key(c)
            assert "edge_vs_market" not in c

    def test_model_unavailable_label_text(self):
        """MODEL_UNAVAILABLE_LABEL constant must be ASCII and mention base rate."""
        MODEL_UNAVAILABLE_LABEL.encode("ascii")
        assert "model unavailable" in MODEL_UNAVAILABLE_LABEL
        assert "base rate" in MODEL_UNAVAILABLE_LABEL
