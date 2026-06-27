"""test_divergence_rank.py -- per-file tests for BB-Q1 divergence_rank.

Acceptance criteria (from BACKLOG BB-Q1):
  - At same tier, higher-edge card ranks above higher model_prob card.
  - sigma=None path does not raise.
  - No dollar / roi / pnl key in output.

Run: python -m pytest tests/platformkit/bestbets/test_divergence_rank.py -q
"""
from __future__ import annotations

import sys
import pathlib

# Ensure the scripts tree is importable when running from the repo root.
_REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from scripts.platformkit.bestbets.divergence_rank import (
    DEFAULT_SIGMA,
    divergence_score,
    rank_cards,
)

# ---------------------------------------------------------------------------
# divergence_score unit tests
# ---------------------------------------------------------------------------

def test_divergence_score_basic():
    """Larger gap -> larger score."""
    score_big = divergence_score(0.70, 0.50)   # gap = 0.20
    score_small = divergence_score(0.55, 0.50)  # gap = 0.05
    assert score_big > score_small


def test_divergence_score_absolute_value():
    """Score is symmetric around gap direction."""
    score_pos = divergence_score(0.70, 0.50)
    score_neg = divergence_score(0.50, 0.70)
    assert abs(score_pos - score_neg) < 1e-9


def test_divergence_score_formula():
    """Exact value check: |0.70 - 0.50| / 0.05 = 4.0."""
    score = divergence_score(0.70, 0.50, sigma=0.05)
    assert abs(score - 4.0) < 1e-9


def test_divergence_score_custom_sigma():
    """sigma=0.10 halves the score vs sigma=0.05."""
    s1 = divergence_score(0.60, 0.50, sigma=0.05)
    s2 = divergence_score(0.60, 0.50, sigma=0.10)
    assert abs(s1 - 2 * s2) < 1e-9


def test_divergence_score_sigma_none_safe():
    """sigma=None must not raise; falls back to DEFAULT_SIGMA."""
    score = divergence_score(0.65, 0.50, sigma=None)
    expected = abs(0.65 - 0.50) / DEFAULT_SIGMA
    assert abs(score - expected) < 1e-9


def test_divergence_score_sigma_zero_safe():
    """sigma=0 must not raise or divide by zero; falls back to DEFAULT_SIGMA."""
    score = divergence_score(0.65, 0.50, sigma=0.0)
    expected = abs(0.65 - 0.50) / DEFAULT_SIGMA
    assert abs(score - expected) < 1e-9


def test_divergence_score_sigma_negative_safe():
    """Negative sigma falls back to DEFAULT_SIGMA."""
    score = divergence_score(0.65, 0.50, sigma=-1.0)
    expected = abs(0.65 - 0.50) / DEFAULT_SIGMA
    assert abs(score - expected) < 1e-9


def test_divergence_score_bad_prob_returns_zero():
    """Non-numeric inputs return 0.0 without raising."""
    assert divergence_score("bad", 0.50) == 0.0
    assert divergence_score(0.70, None) == 0.0  # type: ignore[arg-type]


def test_divergence_score_out_of_range_returns_zero():
    """Probabilities outside [0,1] return 0.0."""
    assert divergence_score(1.5, 0.50) == 0.0
    assert divergence_score(0.70, -0.1) == 0.0


def test_divergence_score_no_banned_keys():
    """divergence_score returns a float, not a dict -- no $ keys possible."""
    result = divergence_score(0.65, 0.50)
    assert isinstance(result, float)
    # Confirm it is not a dict / has no banned keys
    assert not hasattr(result, "keys")


# ---------------------------------------------------------------------------
# rank_cards -- primary acceptance test (edge beats model_prob at same tier)
# ---------------------------------------------------------------------------

def test_rank_cards_edge_beats_model_prob_same_tier():
    """KEY ACCEPTANCE: higher-edge card beats higher model_prob card at same tier.

    Card A: model_prob=0.80, market_prob=0.70 -> edge = 0.10  (small divergence)
    Card B: model_prob=0.70, market_prob=0.50 -> edge = 0.20  (large divergence)

    Both tier "B". After ranking, card B (larger edge) must come first even
    though card A has higher model_prob.
    """
    card_high_prob = {
        "id": "A", "tier": "B", "model_prob": 0.80, "market_prob": 0.70,
    }
    card_high_edge = {
        "id": "B", "tier": "B", "model_prob": 0.70, "market_prob": 0.50,
    }
    ranked = rank_cards([card_high_prob, card_high_edge])

    assert ranked[0]["id"] == "B", (
        "Higher-edge card must rank first at same tier; "
        f"got {[c['id'] for c in ranked]}"
    )


def test_rank_cards_tier_beats_divergence():
    """Tier A card ranks before tier B card regardless of divergence score."""
    card_a = {
        "id": "tier_A", "tier": "A", "model_prob": 0.55, "market_prob": 0.50,
    }
    card_b = {
        "id": "tier_B", "tier": "B", "model_prob": 0.80, "market_prob": 0.50,
    }
    ranked = rank_cards([card_b, card_a])  # pass in reverse order
    assert ranked[0]["id"] == "tier_A"


def test_rank_cards_attaches_divergence_score():
    """rank_cards attaches 'divergence_score' >= 0.0 to each card."""
    card = {"id": "X", "tier": "C", "model_prob": 0.60, "market_prob": 0.50}
    ranked = rank_cards([card])
    assert "divergence_score" in ranked[0]
    assert ranked[0]["divergence_score"] >= 0.0


def test_rank_cards_sigma_none_safe():
    """Cards with no sigma key and sigma=None default_sigma must not raise."""
    cards = [
        {"id": "P", "tier": "A", "model_prob": 0.65, "market_prob": 0.55},
        {"id": "Q", "tier": "A", "model_prob": 0.62, "market_prob": 0.55},
    ]
    # Should not raise; divergence_score handles sigma=None internally
    ranked = rank_cards(cards, default_sigma=None)
    assert len(ranked) == 2
    assert ranked[0]["divergence_score"] >= ranked[1]["divergence_score"]


def test_rank_cards_missing_market_prob_zero_score():
    """Cards missing market_prob get divergence_score=0.0, not an error."""
    card_no_market = {"id": "NM", "tier": "B", "model_prob": 0.80}
    card_full = {"id": "F", "tier": "B", "model_prob": 0.60, "market_prob": 0.50}
    ranked = rank_cards([card_no_market, card_full])
    # Full card has divergence; no-market card gets 0.0
    nm = next(c for c in ranked if c["id"] == "NM")
    assert nm["divergence_score"] == 0.0


def test_rank_cards_empty_returns_empty():
    """Empty input returns empty list without raising."""
    assert rank_cards([]) == []


def test_rank_cards_no_banned_output_keys():
    """No dollar / roi / pnl key in any output card.

    RAILS: UNITS not $. No fabricated profit field.
    """
    cards = [
        {"id": "X", "tier": "B", "model_prob": 0.65, "market_prob": 0.50},
        {"id": "Y", "tier": "A", "model_prob": 0.60, "market_prob": 0.55},
    ]
    ranked = rank_cards(cards)
    banned = {"dollar", "roi", "pnl", "profit", "return", "revenue", "usd"}
    for card in ranked:
        for key in card.keys():
            assert key.lower() not in banned, (
                f"Banned key '{key}' found in output card {card}"
            )


def test_rank_cards_three_tiers_sorted_correctly():
    """Three cards from different tiers come out A -> B -> C."""
    cards = [
        {"id": "C_card", "tier": "C", "model_prob": 0.90, "market_prob": 0.50},
        {"id": "A_card", "tier": "A", "model_prob": 0.55, "market_prob": 0.50},
        {"id": "B_card", "tier": "B", "model_prob": 0.70, "market_prob": 0.50},
    ]
    ranked = rank_cards(cards)
    tiers_in_order = [c["tier"] for c in ranked]
    assert tiers_in_order == ["A", "B", "C"], (
        f"Expected A->B->C tier order, got {tiers_in_order}"
    )


def test_rank_cards_within_tier_higher_edge_first():
    """Multi-card within the same tier: highest edge first."""
    cards = [
        {"id": "low_edge",  "tier": "B", "model_prob": 0.53, "market_prob": 0.50},
        {"id": "mid_edge",  "tier": "B", "model_prob": 0.60, "market_prob": 0.50},
        {"id": "high_edge", "tier": "B", "model_prob": 0.70, "market_prob": 0.50},
    ]
    ranked = rank_cards(cards)
    ids = [c["id"] for c in ranked]
    assert ids[0] == "high_edge", f"Expected high_edge first, got {ids}"
    assert ids[-1] == "low_edge", f"Expected low_edge last, got {ids}"


def test_rank_cards_unknown_tier_sorts_last():
    """Cards with an unrecognised tier sort after A/B/C."""
    cards = [
        {"id": "unknown", "tier": "Z", "model_prob": 0.99, "market_prob": 0.01},
        {"id": "known",   "tier": "C", "model_prob": 0.51, "market_prob": 0.50},
    ]
    ranked = rank_cards(cards)
    assert ranked[0]["id"] == "known"
    assert ranked[1]["id"] == "unknown"
