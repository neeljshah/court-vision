"""Per-file tests for discrimination_guard.py (QA-MLB-DISCRIM).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/bestbets/test_discrimination_guard.py -q

Coverage: NON_DISCRIMINATING/OK/INSUFFICIENT_DATA verdicts; boundary conditions;
mutation guard; forbidden-key scan; robustness against None/garbage/missing probs.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict

import pytest

from scripts.platformkit.bestbets.discrimination_guard import (
    MIN_CARDS_REQUIRED,
    MIN_DISCRIMINATION_RATIO,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_NON_DISCRIMINATING,
    VERDICT_OK,
    check_discrimination,
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


def _make_card(model_prob: float, **extras) -> Dict[str, Any]:
    """Build a minimal BestBetCard-shaped dict."""
    return {"model_prob": model_prob, "game_id": "g1", "sport": "mlb", **extras}


def _make_cards(probs) -> list:
    """Build a list of cards from an iterable of model_prob values."""
    return [_make_card(p) for p in probs]


# ---------------------------------------------------------------------------
# Core acceptance tests
# ---------------------------------------------------------------------------

class TestNonDiscriminating:

    def test_12_cards_4_distinct_probs(self):
        """MLB scenario: 12 cards collapsing to 4 values (ratio=0.333 < 0.5)."""
        probs = [0.4655] * 7 + [0.5123, 0.3210, 0.6789, 0.4000, 0.4655]
        # Re-check: total=12, distinct={0.4655,0.5123,0.3210,0.6789,0.4000}=5; force 4 distinct.
        probs = [0.4655] * 7 + [0.5123, 0.3210, 0.6789, 0.4655]
        # distinct: {0.4655, 0.5123, 0.3210, 0.6789} = 4 out of 11 cards -> ratio 4/11 ~ 0.364
        # Make it exactly 12 cards, 4 distinct.
        probs = [0.4655] * 7 + [0.5123, 0.3210, 0.6789, 0.2000, 0.4655]
        # Recount: 0.4655 x8, 0.5123 x1, 0.3210 x1, 0.6789 x1, 0.2000 x1 = 12 cards, 4 distinct
        # Wait -- 7 + 1 + 1 + 1 + 1 + 1 = 12; distinct = {0.4655,0.5123,0.3210,0.6789,0.2000} = 5.
        # Use task spec: "12 cards -> 4 values". Build explicitly.
        probs = (
            [0.4655] * 5   # dominant (5)
            + [0.5100] * 3  # second  (3)
            + [0.3300] * 2  # third   (2)
            + [0.6700] * 2  # fourth  (2)
        )  # 12 cards, 4 distinct values -> ratio 4/12 = 0.333
        assert len(probs) == 12
        assert len(set(round(p, 6) for p in probs)) == 4

        cards = _make_cards(probs)
        original_cards = copy.deepcopy(cards)

        result = check_discrimination(cards)

        assert result["verdict"] == VERDICT_NON_DISCRIMINATING
        assert result["suppressed"] is True
        assert result["n_cards"] == 12
        assert result["n_distinct_probs"] == 4
        assert result["discrimination_ratio"] == pytest.approx(4 / 12, abs=1e-6)
        assert result["dominant_prob"] == pytest.approx(0.4655, abs=1e-6)
        assert result["n_dominant"] == 5
        assert isinstance(result["reason"], str) and len(result["reason"]) > 0
        # Input must not be mutated
        assert cards == original_cards
        # No forbidden $ keys
        assert not _has_forbidden_key(result)

    def test_single_distinct_prob_all_cards(self):
        """All 15 cards share the same prob -> n_distinct=1; ratio=1/15; NON_DISCRIMINATING."""
        cards = _make_cards([0.5000] * 15)
        result = check_discrimination(cards)
        assert result["verdict"] == VERDICT_NON_DISCRIMINATING
        assert result["suppressed"] is True
        assert result["n_distinct_probs"] == 1
        assert not _has_forbidden_key(result)

    def test_ratio_just_below_threshold(self):
        """4 distinct probs in 9 cards: 4/9 = 0.444 < 0.5 -> NON_DISCRIMINATING."""
        probs = [0.1] * 3 + [0.2] * 3 + [0.3] * 2 + [0.4] * 1
        assert len(probs) == 9
        assert len(set(probs)) == 4
        result = check_discrimination(_make_cards(probs))
        assert result["verdict"] == VERDICT_NON_DISCRIMINATING
        assert result["suppressed"] is True

    def test_reason_mentions_suppressed(self):
        """NON_DISCRIMINATING reason string must be non-empty and ASCII."""
        probs = [0.4655] * 8 + [0.5] * 2  # 10 cards, 2 distinct -> ratio 0.2
        result = check_discrimination(_make_cards(probs))
        assert result["verdict"] == VERDICT_NON_DISCRIMINATING
        reason = result["reason"]
        assert isinstance(reason, str) and reason
        reason.encode("ascii")  # raises UnicodeEncodeError if non-ASCII


class TestOK:

    def test_10_cards_10_distinct_probs(self):
        """10 cards each with a distinct prob: ratio=1.0 >= 0.5 -> OK."""
        probs = [round(0.1 * i, 6) for i in range(1, 11)]  # 0.1..1.0
        cards = _make_cards(probs)
        result = check_discrimination(cards)
        assert result["verdict"] == VERDICT_OK
        assert result["suppressed"] is False
        assert result["n_distinct_probs"] == 10
        assert result["discrimination_ratio"] == pytest.approx(1.0, abs=1e-6)
        assert not _has_forbidden_key(result)

    def test_ratio_exactly_at_threshold_is_ok(self):
        """6 cards, 3 distinct values: ratio=0.5 == min_ratio -> OK (boundary inclusive)."""
        probs = [0.3] * 2 + [0.5] * 2 + [0.7] * 2
        assert len(probs) == 6
        assert len(set(probs)) == 3
        result = check_discrimination(_make_cards(probs))
        assert result["verdict"] == VERDICT_OK
        assert result["suppressed"] is False

    def test_all_distinct_large_slate(self):
        """20 cards all distinct -> OK."""
        probs = [round(i / 20, 6) for i in range(1, 21)]
        result = check_discrimination(_make_cards(probs))
        assert result["verdict"] == VERDICT_OK
        assert result["suppressed"] is False
        assert result["n_distinct_probs"] == 20

    def test_ok_does_not_mutate_input(self):
        """OK path must not mutate card dicts."""
        cards = _make_cards([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
        original = copy.deepcopy(cards)
        check_discrimination(cards)
        assert cards == original


class TestInsufficientData:

    def test_empty_list(self):
        """Empty card list -> INSUFFICIENT_DATA, suppressed=False."""
        result = check_discrimination([])
        assert result["verdict"] == VERDICT_INSUFFICIENT_DATA
        assert result["suppressed"] is False
        assert result["n_cards"] == 0
        assert result["discrimination_ratio"] is None
        assert not _has_forbidden_key(result)

    def test_fewer_than_min_cards(self):
        """Fewer than MIN_CARDS_REQUIRED valid cards -> INSUFFICIENT_DATA."""
        cards = _make_cards([0.5, 0.6])  # 2 cards; MIN_CARDS_REQUIRED=3
        result = check_discrimination(cards)
        assert result["verdict"] == VERDICT_INSUFFICIENT_DATA
        assert result["suppressed"] is False
        assert result["discrimination_ratio"] is None

    def test_all_cards_missing_model_prob(self):
        """Cards without model_prob are excluded; if none remain -> INSUFFICIENT_DATA."""
        cards = [{"game_id": "g1", "sport": "mlb"}] * 10
        result = check_discrimination(cards)
        assert result["verdict"] == VERDICT_INSUFFICIENT_DATA
        assert result["suppressed"] is False

    def test_reason_is_ascii_string_insufficient_data(self):
        """INSUFFICIENT_DATA reason field is non-empty ASCII."""
        result = check_discrimination([])
        reason = result["reason"]
        assert isinstance(reason, str) and reason
        reason.encode("ascii")


class TestRobustness:

    def test_never_raises_on_none_input(self):
        """Passing None as cards must not raise; returns INSUFFICIENT_DATA."""
        result = check_discrimination(None)  # type: ignore[arg-type]
        assert result["verdict"] == VERDICT_INSUFFICIENT_DATA
        assert result["suppressed"] is False

    def test_never_raises_on_non_list_input(self):
        """Passing a dict instead of a list must not raise."""
        result = check_discrimination({"bad": "input"})  # type: ignore[arg-type]
        assert result["verdict"] == VERDICT_INSUFFICIENT_DATA

    def test_cards_with_invalid_model_prob_skipped(self):
        """Cards with None / string / NaN model_prob are skipped gracefully."""
        cards = [
            {"model_prob": None, "sport": "mlb"},
            {"model_prob": "not_a_number", "sport": "mlb"},
            {"model_prob": float("nan"), "sport": "mlb"},
            {"model_prob": float("inf"), "sport": "mlb"},
            # 5 valid ones
            _make_card(0.1), _make_card(0.2), _make_card(0.3),
            _make_card(0.4), _make_card(0.5),
        ]
        # 5 valid cards, all distinct -> ratio=1.0 -> OK
        result = check_discrimination(cards)
        assert result["verdict"] == VERDICT_OK
        assert result["n_cards"] == 5

    def test_non_dict_entries_in_list_ignored(self):
        """Non-dict entries in the card list are silently ignored."""
        cards = [None, 42, "bad", _make_card(0.1), _make_card(0.2), _make_card(0.3)]
        result = check_discrimination(cards)
        # 3 valid cards; MIN_CARDS_REQUIRED=3 -> OK (3 distinct)
        assert result["verdict"] == VERDICT_OK
        assert result["n_cards"] == 3

    def test_no_forbidden_keys_non_discriminating(self):
        """NON_DISCRIMINATING output contains no $ / roi / pnl keys."""
        cards = _make_cards([0.4655] * 10)
        result = check_discrimination(cards)
        assert result["verdict"] == VERDICT_NON_DISCRIMINATING
        assert not _has_forbidden_key(result)

    def test_no_forbidden_keys_ok(self):
        """OK output contains no $ / roi / pnl keys."""
        cards = _make_cards([round(i * 0.05, 6) for i in range(1, 21)])
        result = check_discrimination(cards)
        assert result["verdict"] == VERDICT_OK
        assert not _has_forbidden_key(result)

    def test_output_shape_complete_non_discriminating(self):
        """NON_DISCRIMINATING result always has all required keys."""
        cards = _make_cards([0.5] * 10)
        result = check_discrimination(cards)
        required_keys = {
            "verdict", "suppressed", "n_cards", "n_distinct_probs",
            "discrimination_ratio", "dominant_prob", "n_dominant", "reason",
        }
        assert required_keys.issubset(result.keys())

    def test_output_shape_complete_ok(self):
        """OK result always has all required keys."""
        cards = _make_cards([0.1 * i for i in range(1, 11)])
        result = check_discrimination(cards)
        required_keys = {
            "verdict", "suppressed", "n_cards", "n_distinct_probs",
            "discrimination_ratio", "dominant_prob", "n_dominant", "reason",
        }
        assert required_keys.issubset(result.keys())

    def test_custom_min_ratio_and_min_cards(self):
        """Callers can pass custom thresholds; guard respects them."""
        # 6 cards, 3 distinct; default ratio=3/6=0.5 -> OK.
        # With min_ratio=0.6 -> 3/6=0.5 < 0.6 -> NON_DISCRIMINATING.
        probs = [0.3, 0.3, 0.5, 0.5, 0.7, 0.7]
        result = check_discrimination(_make_cards(probs), min_ratio=0.6)
        assert result["verdict"] == VERDICT_NON_DISCRIMINATING

    def test_min_cards_threshold_respected(self):
        """Callers can lower the min_cards threshold."""
        # 2 cards, both distinct; default MIN_CARDS_REQUIRED=3 -> INSUFFICIENT_DATA.
        # With min_cards=2 -> ratio=2/2=1.0 -> OK.
        result = check_discrimination(_make_cards([0.3, 0.7]), min_cards=2)
        assert result["verdict"] == VERDICT_OK

    def test_discrimination_ratio_type_is_float(self):
        """discrimination_ratio is a float (not int) when a verdict is made."""
        cards = _make_cards([0.1, 0.2, 0.3, 0.4, 0.5])
        result = check_discrimination(cards)
        assert isinstance(result["discrimination_ratio"], float)
