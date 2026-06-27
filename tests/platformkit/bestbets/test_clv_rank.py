"""test_clv_rank.py -- per-file acceptance tests for BB-Q5-1 clv_rank.

Acceptance criteria (from BACKLOG BB-Q5-1):
  1. Two same-tier same-divergence cards: clv.beat_close=True ranks before
     clv_status=INSUFFICIENT_DATA.
  2. INSUFFICIENT_DATA sorts to bottom of its tier (not treated as clv_pct=0).
  3. Higher clv_pct outranks lower among graded cards at same tier.
  4. Tier A beats tier B regardless of CLV.
  5. Empty list -> [].
  6. No $/roi/pnl/profit key in any output (recursive scan).
  7. Never raises on missing clv dict.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/bestbets/test_clv_rank.py -q
"""
from __future__ import annotations

import math
import sys
import pathlib
from typing import Any, Dict, List

_REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from scripts.platformkit.bestbets.clv_rank import (
    rank_cards_clv,
    _recursive_banned_key_check,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEYS = {"dollar", "roi", "pnl", "profit", "return", "revenue", "usd"}


def _make_card(
    id: str,
    tier: str = "B",
    model_prob: float = 0.60,
    market_prob: float = 0.50,
    clv: Dict[str, Any] = None,
) -> Dict[str, Any]:
    card: Dict[str, Any] = {
        "id": id,
        "tier": tier,
        "model_prob": model_prob,
        "market_prob": market_prob,
    }
    if clv is not None:
        card["clv"] = clv
    return card


def _ids(cards: List[Dict[str, Any]]) -> List[str]:
    return [c["id"] for c in cards]


# ---------------------------------------------------------------------------
# 1. beat_close=True graded ranks before INSUFFICIENT_DATA at same tier
# ---------------------------------------------------------------------------

def test_beat_close_ranks_before_insufficient():
    """KEY ACCEPTANCE: graded beat_close=True card ranks before INSUFFICIENT_DATA.

    Both cards are same tier (B) and same divergence (identical model/market probs).
    """
    card_graded = _make_card(
        "graded",
        tier="B",
        model_prob=0.60,
        market_prob=0.50,
        clv={"clv_pct": 0.03, "beat_close": True, "clv_status": "graded"},
    )
    card_insuf = _make_card(
        "insuf",
        tier="B",
        model_prob=0.60,
        market_prob=0.50,
        clv={"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"},
    )
    ranked = rank_cards_clv([card_insuf, card_graded])  # pass insuf first
    assert _ids(ranked)[0] == "graded", (
        f"graded beat_close=True must rank before INSUFFICIENT_DATA; got {_ids(ranked)}"
    )
    assert _ids(ranked)[1] == "insuf"


# ---------------------------------------------------------------------------
# 2. INSUFFICIENT_DATA sinks to bottom of its tier (not fabricated as 0)
# ---------------------------------------------------------------------------

def test_insufficient_data_sinks_below_zero_clv_pct():
    """INSUFFICIENT_DATA must NOT be treated as clv_pct=0.

    A graded card with clv_pct=0.0 (barely graded) must still outrank
    an INSUFFICIENT_DATA card at the same tier and divergence.
    """
    card_zero_pct = _make_card(
        "zero_pct",
        tier="B",
        model_prob=0.60,
        market_prob=0.50,
        clv={"clv_pct": 0.0, "beat_close": False, "clv_status": "graded"},
    )
    card_insuf = _make_card(
        "insuf",
        tier="B",
        model_prob=0.60,
        market_prob=0.50,
        clv={"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"},
    )
    ranked = rank_cards_clv([card_insuf, card_zero_pct])
    assert _ids(ranked)[0] == "zero_pct", (
        "Graded clv_pct=0.0 must outrank INSUFFICIENT_DATA; "
        f"got {_ids(ranked)}"
    )
    assert _ids(ranked)[1] == "insuf"


def test_insufficient_data_sinks_below_negative_clv_pct():
    """Even a graded card with clv_pct=-0.05 outranks INSUFFICIENT_DATA."""
    card_neg = _make_card(
        "neg_pct",
        tier="C",
        model_prob=0.55,
        market_prob=0.50,
        clv={"clv_pct": -0.05, "beat_close": False, "clv_status": "graded"},
    )
    card_insuf = _make_card(
        "insuf",
        tier="C",
        model_prob=0.55,
        market_prob=0.50,
        clv={"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"},
    )
    ranked = rank_cards_clv([card_insuf, card_neg])
    assert _ids(ranked)[0] == "neg_pct", (
        f"Graded clv_pct=-0.05 must outrank INSUFFICIENT_DATA; got {_ids(ranked)}"
    )


# ---------------------------------------------------------------------------
# 3. Higher clv_pct outranks lower among graded cards at same tier
# ---------------------------------------------------------------------------

def test_higher_clv_pct_ranks_first_among_graded():
    """Among graded same-tier same-divergence cards, higher clv_pct ranks first."""
    card_high = _make_card(
        "high_clv",
        tier="B",
        model_prob=0.60,
        market_prob=0.50,
        clv={"clv_pct": 0.08, "beat_close": True, "clv_status": "graded"},
    )
    card_low = _make_card(
        "low_clv",
        tier="B",
        model_prob=0.60,
        market_prob=0.50,
        clv={"clv_pct": 0.02, "beat_close": True, "clv_status": "graded"},
    )
    ranked = rank_cards_clv([card_low, card_high])
    assert _ids(ranked)[0] == "high_clv", (
        f"Higher clv_pct must rank first; got {_ids(ranked)}"
    )


def test_clv_pct_tiebreak_with_multiple_graded():
    """Three graded cards at same tier sort by clv_pct descending."""
    cards = [
        _make_card("low", tier="A", model_prob=0.55, market_prob=0.50,
                   clv={"clv_pct": 0.01, "beat_close": True, "clv_status": "graded"}),
        _make_card("high", tier="A", model_prob=0.55, market_prob=0.50,
                   clv={"clv_pct": 0.09, "beat_close": True, "clv_status": "graded"}),
        _make_card("mid", tier="A", model_prob=0.55, market_prob=0.50,
                   clv={"clv_pct": 0.05, "beat_close": True, "clv_status": "graded"}),
    ]
    ranked = rank_cards_clv(cards)
    assert _ids(ranked) == ["high", "mid", "low"], (
        f"Expected high->mid->low by clv_pct; got {_ids(ranked)}"
    )


# ---------------------------------------------------------------------------
# 4. Tier A beats tier B regardless of CLV
# ---------------------------------------------------------------------------

def test_tier_a_beats_tier_b_regardless_of_clv():
    """Tier dominance: A-tier INSUFFICIENT_DATA beats B-tier graded beat_close=True."""
    card_a_insuf = _make_card(
        "a_insuf",
        tier="A",
        model_prob=0.55,
        market_prob=0.50,
        clv={"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"},
    )
    card_b_graded = _make_card(
        "b_graded",
        tier="B",
        model_prob=0.70,
        market_prob=0.50,
        clv={"clv_pct": 0.15, "beat_close": True, "clv_status": "graded"},
    )
    ranked = rank_cards_clv([card_b_graded, card_a_insuf])
    assert _ids(ranked)[0] == "a_insuf", (
        f"Tier A (even INSUFFICIENT_DATA) must beat tier B; got {_ids(ranked)}"
    )


def test_tier_ordering_a_b_c():
    """Three tiers in shuffled order always come out A->B->C."""
    cards = [
        _make_card("c", tier="C", clv={"clv_pct": 0.20, "beat_close": True, "clv_status": "graded"}),
        _make_card("a", tier="A", clv={"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"}),
        _make_card("b", tier="B", clv={"clv_pct": 0.10, "beat_close": True, "clv_status": "graded"}),
    ]
    ranked = rank_cards_clv(cards)
    assert _ids(ranked) == ["a", "b", "c"], f"Expected A->B->C; got {_ids(ranked)}"


# ---------------------------------------------------------------------------
# 5. Empty list -> []
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty():
    """Empty list must return [] without raising."""
    result = rank_cards_clv([])
    assert result == []


# ---------------------------------------------------------------------------
# 6. No $/roi/pnl/profit key (recursive scan)
# ---------------------------------------------------------------------------

def test_no_banned_keys_in_output():
    """Recursive scan: no dollar/roi/pnl/profit key in any output card or sub-dict."""
    cards = [
        _make_card("x", tier="B", clv={"clv_pct": 0.05, "beat_close": True, "clv_status": "graded"}),
        _make_card("y", tier="A", clv={"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"}),
    ]
    ranked = rank_cards_clv(cards)
    for card in ranked:
        hit = _recursive_banned_key_check(card, _BANNED_KEYS)
        assert hit is None, f"Banned key '{hit}' found in card {card}"


def test_recursive_banned_key_scan_catches_nested():
    """Verify the scan helper itself works on nested dicts."""
    bad_obj = {"a": {"dollar": 5}}
    assert _recursive_banned_key_check(bad_obj, _BANNED_KEYS) == "dollar"

    good_obj = {"clv_pct": 0.03, "beat_close": True}
    assert _recursive_banned_key_check(good_obj, _BANNED_KEYS) is None


# ---------------------------------------------------------------------------
# 7. Never raises on missing clv dict
# ---------------------------------------------------------------------------

def test_missing_clv_dict_does_not_raise():
    """Cards with no 'clv' key at all must not raise."""
    cards = [
        {"id": "no_clv", "tier": "B", "model_prob": 0.60, "market_prob": 0.50},
    ]
    result = rank_cards_clv(cards)
    assert len(result) == 1
    assert result[0]["id"] == "no_clv"


def test_none_clv_dict_does_not_raise():
    """Cards with clv=None must not raise (treated as INSUFFICIENT_DATA)."""
    cards = [
        {"id": "none_clv", "tier": "B", "model_prob": 0.60, "market_prob": 0.50, "clv": None},
    ]
    result = rank_cards_clv(cards)
    assert len(result) == 1


def test_empty_clv_dict_does_not_raise():
    """Cards with clv={} must not raise."""
    cards = [
        {"id": "empty_clv", "tier": "A", "model_prob": 0.65, "market_prob": 0.50, "clv": {}},
    ]
    result = rank_cards_clv(cards)
    assert len(result) == 1


def test_garbage_clv_values_do_not_raise():
    """CLV dict with garbage values must not raise -- degrades gracefully."""
    cards = [
        {
            "id": "garbage",
            "tier": "B",
            "model_prob": 0.60,
            "market_prob": 0.50,
            "clv": {"clv_pct": "NaN", "beat_close": "yes", "clv_status": 42},
        },
    ]
    result = rank_cards_clv(cards)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Additional: divergence_score tiebreak within same CLV bucket
# ---------------------------------------------------------------------------

def test_divergence_score_breaks_tie_among_insufficient():
    """When both cards are INSUFFICIENT_DATA at same tier, higher divergence wins."""
    card_high_div = _make_card(
        "high_div",
        tier="C",
        model_prob=0.70,
        market_prob=0.50,
        clv={"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"},
    )
    card_low_div = _make_card(
        "low_div",
        tier="C",
        model_prob=0.55,
        market_prob=0.50,
        clv={"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"},
    )
    ranked = rank_cards_clv([card_low_div, card_high_div])
    assert _ids(ranked)[0] == "high_div", (
        f"Higher divergence_score must break tie among INSUFFICIENT_DATA; got {_ids(ranked)}"
    )


def test_precomputed_divergence_score_respected():
    """If a card already has 'divergence_score', it is used as-is for the tiebreak."""
    card_big = {"id": "big", "tier": "B",
                "divergence_score": 10.0,
                "clv": {"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"}}
    card_small = {"id": "small", "tier": "B",
                  "divergence_score": 1.0,
                  "clv": {"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"}}
    ranked = rank_cards_clv([card_small, card_big])
    assert _ids(ranked)[0] == "big"


# ---------------------------------------------------------------------------
# Combined scenario: full 4-key sort
# ---------------------------------------------------------------------------

def test_full_sort_scenario():
    """Comprehensive scenario exercising all 4 sort keys.

    Expected order:
      1. A-tier graded high clv (tier A wins)
      2. B-tier beat_close=True high clv (beat_close before not-beat, high clv)
      3. B-tier beat_close=True low clv
      4. B-tier graded not-beat-close
      5. B-tier INSUFFICIENT_DATA high div
      6. B-tier INSUFFICIENT_DATA low div
      7. C-tier anything
    """
    cards = [
        _make_card("b_insuf_low", tier="B", model_prob=0.55, market_prob=0.50,
                   clv={"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"}),
        _make_card("c_any", tier="C", model_prob=0.80, market_prob=0.50,
                   clv={"clv_pct": 0.20, "beat_close": True, "clv_status": "graded"}),
        _make_card("b_beat_high", tier="B", model_prob=0.60, market_prob=0.50,
                   clv={"clv_pct": 0.10, "beat_close": True, "clv_status": "graded"}),
        _make_card("a_graded", tier="A", model_prob=0.60, market_prob=0.50,
                   clv={"clv_pct": 0.05, "beat_close": True, "clv_status": "graded"}),
        _make_card("b_beat_low", tier="B", model_prob=0.60, market_prob=0.50,
                   clv={"clv_pct": 0.02, "beat_close": True, "clv_status": "graded"}),
        _make_card("b_notbeat", tier="B", model_prob=0.60, market_prob=0.50,
                   clv={"clv_pct": 0.04, "beat_close": False, "clv_status": "graded"}),
        _make_card("b_insuf_high", tier="B", model_prob=0.70, market_prob=0.50,
                   clv={"clv_pct": None, "beat_close": None, "clv_status": "INSUFFICIENT_DATA"}),
    ]
    ranked = rank_cards_clv(cards)
    ids = _ids(ranked)

    # Tier A must come first
    assert ids[0] == "a_graded", f"Expected a_graded first; got {ids}"
    # C-tier must be last
    assert ids[-1] == "c_any", f"Expected c_any last; got {ids}"
    # Among B-tier: beat-close cards before not-beat before INSUFFICIENT
    b_cards = [c for c in ranked if c["tier"] == "B"]
    b_ids = _ids(b_cards)
    # beat_close=True cards before beat_close=False before INSUFFICIENT
    beat_close_cards = [c for c in b_cards if c.get("clv", {}).get("beat_close") is True]
    insufficient_cards = [c for c in b_cards if c.get("clv", {}).get("clv_status") == "INSUFFICIENT_DATA"]
    not_beat = [c for c in b_cards
                if c.get("clv", {}).get("clv_status") != "INSUFFICIENT_DATA"
                and c.get("clv", {}).get("beat_close") is not True]

    # All beat-close cards must appear before not-beat-close cards
    last_beat_idx = max(ranked.index(c) for c in beat_close_cards)
    first_notbeat_idx = min(ranked.index(c) for c in not_beat)
    assert last_beat_idx < first_notbeat_idx, (
        f"beat_close=True cards must all appear before not-beat; b_ids={b_ids}"
    )

    # All not-beat cards before INSUFFICIENT
    first_insuf_idx = min(ranked.index(c) for c in insufficient_cards)
    assert first_notbeat_idx < first_insuf_idx, (
        f"not-beat cards must appear before INSUFFICIENT_DATA; b_ids={b_ids}"
    )

    # Among beat-close cards, high clv before low clv
    idx_beat_high = ranked.index(next(c for c in ranked if c["id"] == "b_beat_high"))
    idx_beat_low = ranked.index(next(c for c in ranked if c["id"] == "b_beat_low"))
    assert idx_beat_high < idx_beat_low, (
        f"b_beat_high (clv_pct=0.10) must rank before b_beat_low (0.02); indices {idx_beat_high} vs {idx_beat_low}"
    )

    # Among INSUFFICIENT, high divergence before low
    idx_insuf_high = ranked.index(next(c for c in ranked if c["id"] == "b_insuf_high"))
    idx_insuf_low = ranked.index(next(c for c in ranked if c["id"] == "b_insuf_low"))
    assert idx_insuf_high < idx_insuf_low, (
        f"b_insuf_high (higher div) must rank before b_insuf_low; got {idx_insuf_high} vs {idx_insuf_low}"
    )
