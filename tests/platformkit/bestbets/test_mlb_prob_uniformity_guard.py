"""Per-file tests for mlb_prob_uniformity_guard.py (QAFIX-2-2).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/bestbets/test_mlb_prob_uniformity_guard.py -q

Acceptance criteria:
  * 7 cards sharing model_prob=0.4655 ->
        {uniform:True, dominant_prob:0.4655, n_uniform:7, status:FALLBACK_SUSPECTED}
  * all-distinct probs -> {uniform:False}
  * empty list -> {uniform:False}
  * n_unique==1 -> uniform=True regardless of n_cards
  * no $/roi/pnl key in any output
  * never raises on bad/None input
"""
from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

from scripts.platformkit.bestbets.mlb_prob_uniformity_guard import (
    MIN_CARDS_REQUIRED,
    STATUS_FALLBACK_SUSPECTED,
    STATUS_INSUFFICIENT_DATA,
    STATUS_OK,
    UNIFORM_N_THRESHOLD,
    check_uniformity,
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


def _card(prob: float, **extra) -> Dict[str, Any]:
    return {"model_prob": prob, "game_id": "g1", "sport": "mlb", **extra}


def _cards(probs) -> list:
    return [_card(p) for p in probs]


# ---------------------------------------------------------------------------
# Primary acceptance tests (from the task spec)
# ---------------------------------------------------------------------------

class TestFallbackSuspected:

    def test_7_of_12_cards_share_prob_0_4655(self):
        """QA iter1/8 scenario: 7 of 12 MLB cards share model_prob=0.4655."""
        probs = [0.4655] * 7 + [0.5123, 0.3210, 0.6789, 0.2000, 0.7500]
        assert len(probs) == 12
        cards = _cards(probs)
        original = copy.deepcopy(cards)

        result = check_uniformity(cards)

        assert result["uniform"] is True
        assert abs(result["dominant_prob"] - 0.4655) < 1e-6
        assert result["n_uniform"] == 7
        assert result["status"] == STATUS_FALLBACK_SUSPECTED
        assert isinstance(result["reason"], str) and result["reason"]
        # Input must not be mutated
        assert cards == original
        # No forbidden $ keys
        assert not _has_forbidden_key(result)

    def test_all_cards_same_prob_small_list(self):
        """3 cards all sharing one prob -> FALLBACK_SUSPECTED."""
        cards = _cards([0.5, 0.5, 0.5])
        result = check_uniformity(cards)
        assert result["uniform"] is True
        assert result["status"] == STATUS_FALLBACK_SUSPECTED
        assert result["n_uniform"] == 3
        assert not _has_forbidden_key(result)

    def test_dominant_prob_at_threshold(self):
        """Exactly UNIFORM_N_THRESHOLD (3) cards at one prob -> FALLBACK_SUSPECTED."""
        probs = [0.4] * UNIFORM_N_THRESHOLD + [0.5, 0.6]
        result = check_uniformity(_cards(probs))
        assert result["uniform"] is True
        assert result["status"] == STATUS_FALLBACK_SUSPECTED
        assert result["n_uniform"] == UNIFORM_N_THRESHOLD

    def test_reason_is_ascii_on_flagged_board(self):
        """Reason string on FALLBACK_SUSPECTED must be non-empty and pure ASCII."""
        cards = _cards([0.4655] * 7 + [0.5, 0.6, 0.7, 0.8, 0.9])
        result = check_uniformity(cards)
        assert result["status"] == STATUS_FALLBACK_SUSPECTED
        result["reason"].encode("ascii")  # raises UnicodeEncodeError if non-ASCII


class TestNUnique1AlwaysFlags:
    """n_unique==1 (all cards share the same prob) must flag regardless of n_cards."""

    def test_n_unique_1_single_card(self):
        """Single card -> n_unique=1 -> uniform=True (constant output is certain)."""
        result = check_uniformity(_cards([0.5]))
        assert result["uniform"] is True
        assert result["status"] == STATUS_FALLBACK_SUSPECTED
        assert result["n_unique"] == 1

    def test_n_unique_1_two_cards(self):
        """2 cards same prob -> n_unique=1 -> FALLBACK_SUSPECTED."""
        result = check_uniformity(_cards([0.42, 0.42]))
        assert result["uniform"] is True
        assert result["status"] == STATUS_FALLBACK_SUSPECTED

    def test_n_unique_1_large_slate(self):
        """20 cards all sharing one prob -> n_unique=1 -> FALLBACK_SUSPECTED."""
        result = check_uniformity(_cards([0.3333] * 20))
        assert result["uniform"] is True
        assert result["n_unique"] == 1
        assert result["n_uniform"] == 20


# ---------------------------------------------------------------------------
# All-distinct (OK) path
# ---------------------------------------------------------------------------

class TestAllDistinct:

    def test_all_distinct_probs(self):
        """All unique probs -> uniform=False, status=OK."""
        probs = [0.1 * i for i in range(1, 11)]
        result = check_uniformity(_cards(probs))
        assert result["uniform"] is False
        assert result["status"] == STATUS_OK
        assert not _has_forbidden_key(result)

    def test_just_below_threshold_is_ok(self):
        """Dominant prob appears UNIFORM_N_THRESHOLD-1 times -> OK."""
        n = UNIFORM_N_THRESHOLD - 1
        # Use a dominant prob (0.9999) that cannot collide with any value in the
        # extra list, ensuring the dominant count stays exactly n.
        dominant = 0.9999
        extras = [round(0.1 * i, 6) for i in range(1, 8) if round(0.1 * i, 6) != dominant]
        probs = [dominant] * n + extras
        result = check_uniformity(_cards(probs))
        assert result["uniform"] is False
        assert result["status"] == STATUS_OK

    def test_ok_does_not_mutate_input(self):
        """OK path must not mutate card dicts."""
        cards = _cards([0.1, 0.2, 0.3, 0.4, 0.5])
        original = copy.deepcopy(cards)
        check_uniformity(cards)
        assert cards == original

    def test_ok_no_forbidden_keys(self):
        """OK output contains no forbidden $ keys."""
        result = check_uniformity(_cards([0.1, 0.2, 0.3, 0.4, 0.5]))
        assert not _has_forbidden_key(result)


# ---------------------------------------------------------------------------
# Empty / insufficient data
# ---------------------------------------------------------------------------

class TestEmptyAndInsufficient:

    def test_empty_list(self):
        """Empty card list -> uniform=False, status=INSUFFICIENT_DATA."""
        result = check_uniformity([])
        assert result["uniform"] is False
        assert result["status"] == STATUS_INSUFFICIENT_DATA
        assert result["dominant_prob"] is None
        assert result["n_uniform"] == 0
        assert not _has_forbidden_key(result)

    def test_none_input(self):
        """None input must not raise; returns uniform=False."""
        result = check_uniformity(None)  # type: ignore[arg-type]
        assert result["uniform"] is False
        assert result["status"] == STATUS_INSUFFICIENT_DATA

    def test_all_cards_missing_model_prob(self):
        """Cards without model_prob produce no valid probs -> INSUFFICIENT_DATA."""
        cards = [{"game_id": "g1", "sport": "mlb"}] * 5
        result = check_uniformity(cards)
        assert result["uniform"] is False
        assert result["status"] == STATUS_INSUFFICIENT_DATA

    def test_insufficient_data_no_forbidden_keys(self):
        """INSUFFICIENT_DATA output has no forbidden $ keys."""
        assert not _has_forbidden_key(check_uniformity([]))


# ---------------------------------------------------------------------------
# Output shape completeness
# ---------------------------------------------------------------------------

class TestOutputShape:

    REQUIRED_KEYS = frozenset({
        "uniform", "dominant_prob", "n_uniform", "n_cards", "n_unique",
        "status", "reason",
    })

    def test_fallback_suspected_shape(self):
        result = check_uniformity(_cards([0.5] * 5 + [0.6, 0.7]))
        assert self.REQUIRED_KEYS.issubset(result.keys())

    def test_ok_shape(self):
        result = check_uniformity(_cards([0.1, 0.2, 0.3, 0.4, 0.5]))
        assert self.REQUIRED_KEYS.issubset(result.keys())

    def test_insufficient_data_shape(self):
        result = check_uniformity([])
        assert self.REQUIRED_KEYS.issubset(result.keys())


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

class TestRobustness:

    def test_cards_with_invalid_model_prob_skipped(self):
        """None / string / NaN / Inf model_prob cards are skipped gracefully."""
        bad = [
            {"model_prob": None, "sport": "mlb"},
            {"model_prob": "not_a_number", "sport": "mlb"},
            {"model_prob": float("nan"), "sport": "mlb"},
            {"model_prob": float("inf"), "sport": "mlb"},
        ]
        # Add enough valid cards to avoid INSUFFICIENT_DATA
        valid = _cards([0.1, 0.2, 0.3, 0.4, 0.5])
        result = check_uniformity(bad + valid)
        assert result["n_cards"] == 5  # only the 5 valid ones counted
        assert result["status"] == STATUS_OK

    def test_non_dict_entries_ignored(self):
        """Non-dict entries in the card list are silently ignored."""
        cards = [None, 42, "bad_card"] + _cards([0.3, 0.3, 0.3, 0.5, 0.7])
        result = check_uniformity(cards)
        # 3 cards at 0.3, which >= UNIFORM_N_THRESHOLD -> FALLBACK_SUSPECTED
        assert result["status"] == STATUS_FALLBACK_SUSPECTED

    def test_custom_uniform_n_threshold(self):
        """Callers can lower uniform_n; guard respects it."""
        # 2 cards at same prob; default threshold=3 -> OK.
        # With uniform_n=2 -> FALLBACK_SUSPECTED.
        result = check_uniformity(_cards([0.5, 0.5, 0.6, 0.7]), uniform_n=2)
        assert result["uniform"] is True
        assert result["status"] == STATUS_FALLBACK_SUSPECTED

    def test_dominant_prob_type_is_float_when_uniform(self):
        """dominant_prob is a float (not None) on FALLBACK_SUSPECTED."""
        result = check_uniformity(_cards([0.4655] * 7 + [0.5, 0.6, 0.7, 0.8, 0.9]))
        assert isinstance(result["dominant_prob"], float)

    def test_reason_ascii_on_ok(self):
        """OK reason is pure ASCII."""
        result = check_uniformity(_cards([0.1, 0.2, 0.3, 0.4, 0.5]))
        result["reason"].encode("ascii")

    def test_reason_ascii_on_insufficient(self):
        """INSUFFICIENT_DATA reason is pure ASCII."""
        result = check_uniformity([])
        result["reason"].encode("ascii")

    def test_never_raises_on_dict_input(self):
        """Passing a dict instead of a list must not raise."""
        result = check_uniformity({"bad": "input"})  # type: ignore[arg-type]
        assert result["uniform"] is False
