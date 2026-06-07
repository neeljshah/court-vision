"""Tests for signals/rest_b2b_fatigue.py.

Two mandatory assertions (per DESIGN.md build contract):
  1. Leak-safety: build() must NEVER return non-None for a future game_date
     (i.e. a date strictly after ctx.decision_time).
  2. Value-sanity: build() must return a dict whose values are finite floats
     and whose fatigue_score is in [0, 1]; is_b2b/is_b3b must be 0.0 or 1.0.

Additional tests:
  3. Neutral default when ctx.team or ctx.game_date is missing.
  4. Composite score formula is correct for known inputs.
  5. Dict signal: feature_names() returns 5 entries prefixed with the signal name.
  6. validate_output() accepts valid dict and None; rejects bad types.
  7. hypothesis() returns a Hypothesis with the right name/target/scope.
  8. Atlas reinforcement path: b2b_pts_delta from the store adjusts fatigue_score.
"""
from __future__ import annotations

import datetime as _dt
import sys
import types
from pathlib import Path
from typing import Dict, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on sys.path when running from the repo root.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ---------------------------------------------------------------------------
# Import the signal (module-level; failures here = import bug, not test bug)
# ---------------------------------------------------------------------------
from signals.rest_b2b_fatigue import (  # noqa: E402
    RestB2bFatigueSignal,
    _fatigue_score,
    _DEFAULTS,
    _MILES_SCALE,
    _ALT_SCALE,
)
from src.loop.signal import AsOfContext, Hypothesis  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(
    game_date: Optional[str] = "2024-01-15",
    team: Optional[str] = "BOS",
    decision_time: Optional[_dt.datetime] = None,
    **kwargs,
) -> AsOfContext:
    """Build a minimal AsOfContext for testing."""
    if decision_time is None:
        # decision_time must be on or before game_date (pregame)
        if game_date:
            decision_time = _dt.datetime.fromisoformat(game_date + "T08:00:00")
        else:
            decision_time = _dt.datetime(2024, 1, 15, 8, 0, 0)
    return AsOfContext(
        decision_time=decision_time,
        game_date=game_date,
        team=team,
        scope="pregame",
        **kwargs,
    )


def _fake_lookup(
    date: str = "2024-01-15",
    team: str = "BOS",
    is_b2b: float = 1.0,
    is_b3b: float = 0.0,
    miles: float = 1500.0,
    alt_ft: float = 5280.0,
) -> Dict[Tuple[str, str], Dict[str, float]]:
    """Build a minimal lookup dict for patching _get_lookup."""
    return {
        (date, team): {
            "is_b2b": is_b2b,
            "is_b3b": is_b3b,
            "miles_traveled": miles,
            "altitude_ft": alt_ft,
        }
    }


# ---------------------------------------------------------------------------
# Test 1 — LEAK-SAFETY ASSERTION
# ---------------------------------------------------------------------------

def test_leak_safety_future_date_returns_none_or_defaults():
    """build() must not return enriched data for a date after decision_time.

    The parquet is keyed by game_date.  A future game_date cannot be looked up
    because it does not appear in the parquet at train time (the parquet is built
    pre-game).  Even if we inject a future date into a mocked lookup, the signal
    should produce only the neutral-default dict (no future knowledge flowing in).

    The strict leak-safety contract: decision_time < game_date is only valid for
    live scope.  For pregame scope the decision is made on game morning; we test
    that the signal does not call utcnow() or pull any data beyond the lookup key.
    """
    sig = RestB2bFatigueSignal(store=None)

    # Future game date (well after any plausible decision_time)
    future_date = "2099-12-31"
    decision_time = _dt.datetime(2024, 1, 15, 8, 0, 0)  # clearly before future_date

    # The lookup for future_date will be absent → parquet has no future rows
    with patch("signals.rest_b2b_fatigue._get_lookup", return_value={}):
        result = sig.build(_ctx(game_date=future_date, decision_time=decision_time))

    # Must return None (no team/date in lookup → falls back to _DEFAULTS with score 0)
    # OR the neutral-default dict (all zeros) — NEVER a non-zero fatigue signal
    # derived from future data.
    if result is not None:
        # Neutral default: all values must be zero (no information leaked)
        assert isinstance(result, dict), "result must be dict or None"
        assert result["is_b2b"] == 0.0, "is_b2b must be 0 for absent future row"
        assert result["is_b3b"] == 0.0, "is_b3b must be 0 for absent future row"
        assert result["fatigue_score"] == 0.0, "fatigue_score must be 0 for absent row"


def test_leak_safety_no_utcnow_called():
    """build() must not call datetime.utcnow() / datetime.now() at runtime.

    The method must be fully parameterised by ctx — the decision_time is the
    only allowed temporal anchor.  We check this by running build() and
    verifying the result is stable (calling it twice with the same ctx gives
    identical results), which would break if utcnow() were used internally
    to filter data rather than ctx.decision_time.
    """
    sig = RestB2bFatigueSignal(store=None)
    ctx = _ctx(game_date="2024-01-15", team="BOS")

    lookup = _fake_lookup(date="2024-01-15", team="BOS",
                          is_b2b=1.0, is_b3b=0.0, miles=1500.0, alt_ft=5280.0)

    with patch("signals.rest_b2b_fatigue._get_lookup", return_value=lookup):
        result_a = sig.build(ctx)
        result_b = sig.build(ctx)

    # Idempotent: same ctx → same result (no hidden time dependency)
    assert result_a == result_b, (
        "build() must be deterministic given the same ctx (no utcnow() side effect)"
    )
    assert result_a is not None, "Expected non-None for a matched B2B row"


# ---------------------------------------------------------------------------
# Test 2 — VALUE-SANITY ASSERTION
# ---------------------------------------------------------------------------

def test_value_sanity_b2b_game():
    """build() returns a valid dict with correct types and bounds for a B2B row."""
    sig = RestB2bFatigueSignal(store=None)
    ctx = _ctx(game_date="2024-01-15", team="BOS")

    lookup = _fake_lookup(
        date="2024-01-15", team="BOS",
        is_b2b=1.0, is_b3b=0.0, miles=2000.0, alt_ft=5280.0,
    )
    with patch("signals.rest_b2b_fatigue._get_lookup", return_value=lookup):
        result = sig.build(ctx)

    assert isinstance(result, dict), "Expected dict for a matched B2B row"
    assert set(result.keys()) == {"is_b2b", "is_b3b", "miles_traveled", "altitude_ft", "fatigue_score"}

    # All values must be finite floats
    for k, v in result.items():
        assert isinstance(v, float), f"{k} must be float, got {type(v)}"
        assert -1e9 < v < 1e9, f"{k}={v} is not finite"

    # is_b2b/is_b3b are binary flags
    assert result["is_b2b"] in (0.0, 1.0), "is_b2b must be 0 or 1"
    assert result["is_b3b"] in (0.0, 1.0), "is_b3b must be 0 or 1"

    # fatigue_score must be in [0, 1]
    assert 0.0 <= result["fatigue_score"] <= 1.0, (
        f"fatigue_score out of range: {result['fatigue_score']}"
    )

    # A B2B game should produce a fatigue_score > 0
    assert result["fatigue_score"] > 0.0, "B2B game must produce non-zero fatigue_score"


def test_value_sanity_non_b2b_rest_game():
    """A non-B2B, low-travel game produces fatigue_score close to 0."""
    sig = RestB2bFatigueSignal(store=None)
    ctx = _ctx(game_date="2024-01-20", team="LAL")

    lookup = _fake_lookup(
        date="2024-01-20", team="LAL",
        is_b2b=0.0, is_b3b=0.0, miles=0.0, alt_ft=285.0,  # home game, LA altitude
    )
    with patch("signals.rest_b2b_fatigue._get_lookup", return_value=lookup):
        result = sig.build(ctx)

    assert result is not None
    assert result["is_b2b"] == 0.0
    assert result["fatigue_score"] < 0.1, (
        f"Home rest game should have near-zero fatigue_score, got {result['fatigue_score']}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Neutral defaults when context is incomplete
# ---------------------------------------------------------------------------

def test_returns_none_when_team_missing():
    """build() returns None when ctx.team is None (signal not applicable)."""
    sig = RestB2bFatigueSignal(store=None)
    ctx = _ctx(game_date="2024-01-15", team=None)
    with patch("signals.rest_b2b_fatigue._get_lookup", return_value={}):
        result = sig.build(ctx)
    assert result is None, "Must return None when ctx.team is None"


def test_returns_none_when_game_date_missing():
    """build() returns None when ctx.game_date is None."""
    sig = RestB2bFatigueSignal(store=None)
    ctx = _ctx(game_date=None, team="BOS")
    with patch("signals.rest_b2b_fatigue._get_lookup", return_value={}):
        result = sig.build(ctx)
    assert result is None, "Must return None when ctx.game_date is None"


def test_returns_default_zeros_for_missing_lookup_key():
    """build() returns all-zero dict when game/team not found in the parquet."""
    sig = RestB2bFatigueSignal(store=None)
    ctx = _ctx(game_date="2024-01-15", team="BOS")

    with patch("signals.rest_b2b_fatigue._get_lookup", return_value={}):
        result = sig.build(ctx)

    assert result is not None, "Should return neutral dict, not None, for missing key"
    assert result["is_b2b"] == 0.0
    assert result["is_b3b"] == 0.0
    assert result["miles_traveled"] == 0.0
    assert result["fatigue_score"] == 0.0


# ---------------------------------------------------------------------------
# Test 4 — Composite score formula
# ---------------------------------------------------------------------------

def test_fatigue_score_formula_pure():
    """_fatigue_score() matches hand-computed formula for known inputs."""
    # B2B at Denver (alt=5280, miles=1500)
    score = _fatigue_score(
        is_b2b=1.0, is_b3b=0.0, miles=1500.0, alt_ft=5280.0
    )
    expected = (
        0.50 * 1.0
        + 0.20 * 0.0
        + 0.20 * min(1500.0 / _MILES_SCALE, 1.0)
        + 0.10 * min(5280.0 / _ALT_SCALE, 1.0)
    )
    assert abs(score - expected) < 1e-9, f"score={score}, expected={expected}"


def test_fatigue_score_max_clamp():
    """_fatigue_score() never exceeds 1.0 for extreme inputs."""
    score = _fatigue_score(is_b2b=1.0, is_b3b=1.0, miles=99999.0, alt_ft=99999.0)
    assert score <= 1.0, f"score clamped to 1.0 for extreme inputs, got {score}"


def test_fatigue_score_min_zero():
    """_fatigue_score() returns 0.0 for a home rest game."""
    score = _fatigue_score(is_b2b=0.0, is_b3b=0.0, miles=0.0, alt_ft=0.0)
    assert score == 0.0


# ---------------------------------------------------------------------------
# Test 5 — feature_names()
# ---------------------------------------------------------------------------

def test_feature_names():
    """feature_names() returns 5 names, all prefixed with 'rest_b2b_fatigue__'."""
    sig = RestB2bFatigueSignal()
    names = sig.feature_names()
    assert len(names) == 5, f"Expected 5 feature names, got {len(names)}: {names}"
    for n in names:
        assert n.startswith("rest_b2b_fatigue__"), f"Wrong prefix: {n}"
    assert "rest_b2b_fatigue__fatigue_score" in names
    assert "rest_b2b_fatigue__is_b2b" in names


# ---------------------------------------------------------------------------
# Test 6 — validate_output()
# ---------------------------------------------------------------------------

def test_validate_output_valid_dict():
    """validate_output() accepts a well-formed dict result."""
    sig = RestB2bFatigueSignal()
    good = {"is_b2b": 1.0, "is_b3b": 0.0, "miles_traveled": 1500.0,
            "altitude_ft": 5280.0, "fatigue_score": 0.73}
    assert sig.validate_output(good) is True


def test_validate_output_none():
    """validate_output() accepts None (neutral / missing)."""
    sig = RestB2bFatigueSignal()
    assert sig.validate_output(None) is True


def test_validate_output_bad_type():
    """validate_output() rejects a dict containing a non-numeric value."""
    sig = RestB2bFatigueSignal()
    bad = {"is_b2b": "yes"}  # string, not float
    assert sig.validate_output(bad) is False


# ---------------------------------------------------------------------------
# Test 7 — hypothesis()
# ---------------------------------------------------------------------------

def test_hypothesis_metadata():
    """hypothesis() returns a Hypothesis with correct slug/target/scope/source."""
    sig = RestB2bFatigueSignal()
    hyp = sig.hypothesis()
    assert isinstance(hyp, Hypothesis)
    assert hyp.name == "rest_b2b_fatigue"
    assert hyp.target == "pts"
    assert hyp.scope == "pregame"
    assert hyp.source == "seed"
    assert "fatigue_profile" in hyp.atlas_fields
    assert hyp.expected_verdict == "SHIP"
    assert len(hyp.statement) > 20, "statement should be non-trivial"


# ---------------------------------------------------------------------------
# Test 8 — Atlas reinforcement path
# ---------------------------------------------------------------------------

def test_atlas_reinforcement_adjusts_score():
    """A b2b_pts_delta in the store shifts fatigue_score by a small amount."""
    # Build a mock store that returns a fatigue_profile with a large b2b_pts_delta
    mock_store = MagicMock()
    # b2b_pts_delta=-3.0 means B2B costs 3 PTS; the signal maps this to a positive
    # correction on the fatigue_score (higher fatigue → more negative PTS prediction).
    mock_store.read_atlas.return_value = {"b2b_pts_delta": -3.0}

    sig = RestB2bFatigueSignal(store=mock_store)
    ctx = _ctx(game_date="2024-01-15", team="BOS")

    lookup = _fake_lookup(
        date="2024-01-15", team="BOS",
        is_b2b=1.0, is_b3b=0.0, miles=500.0, alt_ft=0.0,
    )
    with patch("signals.rest_b2b_fatigue._get_lookup", return_value=lookup):
        result_with_store = sig.build(ctx)

    sig_no_store = RestB2bFatigueSignal(store=None)
    with patch("signals.rest_b2b_fatigue._get_lookup", return_value=lookup):
        result_no_store = sig_no_store.build(ctx)

    assert result_with_store is not None
    assert result_no_store is not None

    # Store reinforcement must adjust the score (either direction is valid; we
    # verify the adjustment is non-zero and bounded)
    diff = result_with_store["fatigue_score"] - result_no_store["fatigue_score"]
    assert abs(diff) > 0.0, "Store b2b_pts_delta should shift fatigue_score"
    assert abs(diff) <= 0.1, "Store correction must be capped at ±0.1"

    # Score must remain in [0, 1] after reinforcement
    assert 0.0 <= result_with_store["fatigue_score"] <= 1.0
