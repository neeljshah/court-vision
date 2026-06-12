"""
tests/kernel/test_invariants.py
--------------------------------
Hermetic, offline tests for kernel/testing/invariants.py.
Uses only toy in-memory data — no domains, no network, no heavy deps.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict

import pytest

from kernel.testing.invariants import (
    check_frozen,
    check_monotonic_nonincreasing,
    check_prefix_running_scores,
    check_registry_order,
    check_truncation_invariance,
    fold_scores,
)

# ---------------------------------------------------------------------------
# Toy event fixtures
# ---------------------------------------------------------------------------
# Each event is a plain dict with:
#   "pts"   – points scored on this play
#   "side"  – "home" or "away"
#   "run_h" – cumulative home score after this play
#   "run_a" – cumulative away score after this play

TOY_EVENTS = [
    {"pts": 2, "side": "home", "run_h": 2,  "run_a": 0},
    {"pts": 3, "side": "away", "run_h": 2,  "run_a": 3},
    {"pts": 2, "side": "away", "run_h": 2,  "run_a": 5},
    {"pts": 1, "side": "home", "run_h": 3,  "run_a": 5},
    {"pts": 2, "side": "home", "run_h": 5,  "run_a": 5},
]
# Final totals: home=5, away=5


def _pts(e: Dict) -> int:
    return e["pts"]


def _side(e: Dict) -> str:
    return e["side"]


def _running(e: Dict, side: str) -> int:
    return e["run_h"] if side == "home" else e["run_a"]


# ---------------------------------------------------------------------------
# fold_scores
# ---------------------------------------------------------------------------

class TestFoldScores:
    def test_basic_totals(self) -> None:
        result = fold_scores(TOY_EVENTS, _pts, _side)
        assert result == {"home": 5, "away": 5}

    def test_single_side_only(self) -> None:
        events = [{"pts": 3, "side": "home"}] * 4
        result = fold_scores(events, _pts, _side)
        assert result == {"home": 12}

    def test_empty_sequence(self) -> None:
        assert fold_scores([], _pts, _side) == {}

    def test_accumulates_correctly(self) -> None:
        # Verify incremental accumulation order doesn't matter
        events = [
            {"pts": 10, "side": "x"},
            {"pts": 5,  "side": "y"},
            {"pts": 3,  "side": "x"},
        ]
        result = fold_scores(events, _pts, _side)
        assert result["x"] == 13
        assert result["y"] == 5


# ---------------------------------------------------------------------------
# check_truncation_invariance
# ---------------------------------------------------------------------------

class TestTruncationInvariance:
    def test_passes_on_consistent_data(self) -> None:
        passed, detail = check_truncation_invariance(
            TOY_EVENTS, _pts, _side, {"home": 5, "away": 5}
        )
        assert passed is True
        assert "mismatches" not in detail

    def test_fails_when_expected_too_high(self) -> None:
        passed, detail = check_truncation_invariance(
            TOY_EVENTS, _pts, _side, {"home": 99, "away": 5}
        )
        assert passed is False
        assert "home" in detail["mismatches"]

    def test_fails_when_expected_too_low(self) -> None:
        passed, detail = check_truncation_invariance(
            TOY_EVENTS, _pts, _side, {"home": 5, "away": 1}
        )
        assert passed is False
        assert "away" in detail["mismatches"]

    def test_fails_on_unknown_expected_side(self) -> None:
        # expected includes a side that never scored
        passed, detail = check_truncation_invariance(
            TOY_EVENTS, _pts, _side, {"home": 5, "away": 5, "neutral": 0}
        )
        # "neutral" totals 0 in expected; fold returns no key → mismatch
        # Actually fold returns 0 default vs expected 0 — should pass
        # Let's validate the actual logic: fold won't have "neutral" key
        # so actual.get("neutral") is None != 0 → mismatch → False
        assert passed is False

    def test_detail_always_has_actual_and_expected(self) -> None:
        _, detail = check_truncation_invariance(
            TOY_EVENTS, _pts, _side, {"home": 5, "away": 5}
        )
        assert "actual" in detail
        assert "expected" in detail

    def test_empty_events_zero_expected(self) -> None:
        passed, _ = check_truncation_invariance(
            [], _pts, _side, {}
        )
        assert passed is True


# ---------------------------------------------------------------------------
# check_prefix_running_scores
# ---------------------------------------------------------------------------

class TestPrefixRunningScores:
    def test_all_cuts_pass_on_consistent_data(self) -> None:
        cuts = [1, 2, 3, 4, 5]
        results = check_prefix_running_scores(
            TOY_EVENTS, _pts, _side, _running, cuts
        )
        assert results, "should produce entries"
        assert all(passed for *_, passed in results), (
            f"Some prefix checks failed: {[(c,s,f,r,p) for c,s,f,r,p in results if not p]}"
        )

    def test_single_cut(self) -> None:
        results = check_prefix_running_scores(
            TOY_EVENTS, _pts, _side, _running, [3]
        )
        # After 3 events: home=2, away=5
        for cut, side, folded, recorded, passed in results:
            assert cut == 3
            assert passed, f"cut={cut} side={side} folded={folded} recorded={recorded}"

    def test_inconsistent_running_score_fails(self) -> None:
        # Corrupt the running score on event index 2 (cut=3 anchor)
        corrupt = list(TOY_EVENTS)
        corrupt[2] = {**TOY_EVENTS[2], "run_a": 999}  # wrong recorded value
        results = check_prefix_running_scores(
            corrupt, _pts, _side, _running, [3]
        )
        # The away folded total (5) won't match recorded (999)
        failures = [(c, s, f, r, p) for c, s, f, r, p in results if not p]
        assert any(s == "away" for _, s, _, _, _ in failures)

    def test_out_of_range_cuts_skipped(self) -> None:
        results = check_prefix_running_scores(
            TOY_EVENTS, _pts, _side, _running, [0, 6, 100]
        )
        assert results == []

    def test_empty_cuts(self) -> None:
        results = check_prefix_running_scores(
            TOY_EVENTS, _pts, _side, _running, []
        )
        assert results == []


# ---------------------------------------------------------------------------
# check_registry_order
# ---------------------------------------------------------------------------

class TestRegistryOrder:
    def test_matching_order_returns_true(self) -> None:
        names = ("pts", "reb", "ast")
        assert check_registry_order(names, ("pts", "reb", "ast")) is True

    def test_different_order_returns_false(self) -> None:
        names = ("pts", "reb", "ast")
        assert check_registry_order(names, ("reb", "pts", "ast")) is False

    def test_extra_element_returns_false(self) -> None:
        assert check_registry_order(("a", "b", "c"), ("a", "b")) is False

    def test_empty_matches_empty(self) -> None:
        assert check_registry_order([], []) is True

    def test_list_and_tuple_equivalent(self) -> None:
        assert check_registry_order(["x", "y"], ("x", "y")) is True


# ---------------------------------------------------------------------------
# check_frozen
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class _FrozenDC:
    value: int = 0


@dataclasses.dataclass
class _MutableDC:
    value: int = 0


class TestCheckFrozen:
    def test_frozen_dataclass_returns_true(self) -> None:
        assert check_frozen(_FrozenDC(value=1)) is True

    def test_mutable_dataclass_returns_false(self) -> None:
        assert check_frozen(_MutableDC(value=1)) is False

    def test_plain_object_returns_false(self) -> None:
        class Plain:
            pass
        assert check_frozen(Plain()) is False

    def test_simple_class_with_setattr_override(self) -> None:
        class AlwaysFrozen:
            def __setattr__(self, name: str, value: Any) -> None:
                raise dataclasses.FrozenInstanceError("immutable")

        assert check_frozen(AlwaysFrozen()) is True


# ---------------------------------------------------------------------------
# check_monotonic_nonincreasing
# ---------------------------------------------------------------------------

class TestMonotonicNonincreasing:
    def test_strictly_decreasing(self) -> None:
        assert check_monotonic_nonincreasing([1.0, 0.75, 0.5, 0.25, 0.0]) is True

    def test_flat_sequence(self) -> None:
        assert check_monotonic_nonincreasing([0.5, 0.5, 0.5]) is True

    def test_mixed_flat_and_decreasing(self) -> None:
        assert check_monotonic_nonincreasing([1.0, 1.0, 0.8, 0.5, 0.5, 0.0]) is True

    def test_increasing_returns_false(self) -> None:
        assert check_monotonic_nonincreasing([0.0, 0.5, 1.0]) is False

    def test_spike_in_middle_returns_false(self) -> None:
        assert check_monotonic_nonincreasing([1.0, 0.5, 0.8, 0.2]) is False

    def test_empty_sequence(self) -> None:
        assert check_monotonic_nonincreasing([]) is True

    def test_single_element(self) -> None:
        assert check_monotonic_nonincreasing([0.42]) is True

    def test_integer_values(self) -> None:
        assert check_monotonic_nonincreasing([10, 9, 8, 7]) is True
        assert check_monotonic_nonincreasing([10, 9, 11, 7]) is False
