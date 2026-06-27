"""Per-file tests for scripts.platformkit.pm_trading.stake_units_normalize.

Run ONLY this file (the full suite freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_stake_units_normalize.py -q

Acceptance criteria (QA iter 9 P1):
  normalize(382.32, unit_size=100) -> 3.82 (within 0-10 band)
  normalize(5000.0, 100)           -> clamped to <= 10
  normalize(0.0)                   -> 0.0
  output never exceeds band_max
  output is a bare float (no $ string)
"""
from __future__ import annotations

import math
import pytest

from scripts.platformkit.pm_trading.stake_units_normalize import (
    DEFAULT_UNIT_SIZE,
    UNIT_BAND_MAX,
    normalize,
)


# ---------------------------------------------------------------------------
# Core acceptance tests
# ---------------------------------------------------------------------------

def test_normalize_typical_kelly_dollar():
    """$382.32 / $100 unit = 3.8232 units -- within the 0-10 band."""
    result = normalize(382.32, unit_size=100)
    assert abs(result - 3.8232) < 1e-5, "expected ~3.8232, got %r" % result
    assert 0.0 <= result <= 10.0


def test_normalize_large_stake_clamped():
    """$5000 / $100 = 50 units but band_max=10 clamps to 10.0."""
    result = normalize(5000.0, unit_size=100)
    assert result <= 10.0, "expected clamped <= 10.0, got %r" % result
    assert result == 10.0


def test_normalize_zero_returns_zero():
    """Zero dollar stake -> 0.0 units."""
    result = normalize(0.0)
    assert result == 0.0


# ---------------------------------------------------------------------------
# Band invariant: output never exceeds band_max
# ---------------------------------------------------------------------------

def test_output_never_exceeds_band_for_extreme_values():
    """Random large values must all clamp to UNIT_BAND_MAX."""
    huge_stakes = [1_000.0, 10_000.0, 100_000.0, 1_000_000.0]
    for s in huge_stakes:
        r = normalize(s, unit_size=100)
        assert r <= UNIT_BAND_MAX, (
            "normalize(%s) returned %r > UNIT_BAND_MAX=%s" % (s, r, UNIT_BAND_MAX)
        )


def test_output_never_below_zero():
    """Zero is the floor; we also verify that 0 edge case stays 0."""
    assert normalize(0.0, unit_size=100) == 0.0
    assert normalize(0.0, unit_size=1.0) == 0.0


# ---------------------------------------------------------------------------
# Return type: bare float (no $ string, no special wrapper)
# ---------------------------------------------------------------------------

def test_return_type_is_bare_float():
    """Output must be a plain Python float, not a string or formatted value."""
    result = normalize(382.32, unit_size=100)
    assert isinstance(result, float), "expected float, got %r" % type(result)


def test_return_type_zero_is_float():
    result = normalize(0.0)
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Additional correctness cases
# ---------------------------------------------------------------------------

def test_exact_one_unit():
    """$100 / $100 unit = exactly 1.0."""
    assert normalize(100.0, unit_size=100) == 1.0


def test_fractional_units():
    """$50 / $100 unit = 0.5 units."""
    assert abs(normalize(50.0, unit_size=100) - 0.5) < 1e-9


def test_custom_unit_size():
    """unit_size=250: $500 -> 2.0 units."""
    result = normalize(500.0, unit_size=250.0)
    assert abs(result - 2.0) < 1e-9


def test_custom_band_max():
    """A tighter band_max of 5.0 clamps earlier."""
    result = normalize(1000.0, unit_size=100, band_max=5.0)
    assert result == 5.0


def test_at_band_boundary():
    """$1000 / $100 = exactly 10.0 -- sits exactly on band_max, not clamped lower."""
    result = normalize(1000.0, unit_size=100)
    assert result == 10.0


def test_just_above_band_boundary():
    """$1001 / $100 = 10.01 -> clamped to 10.0."""
    result = normalize(1001.0, unit_size=100)
    assert result == 10.0


def test_small_sub_unit_stake():
    """$1 / $100 = 0.01 units -- small but not zero."""
    result = normalize(1.0, unit_size=100)
    assert abs(result - 0.01) < 1e-9


def test_result_rounded_to_six_decimal_places():
    """Irrational division is rounded to at most 6 d.p. -- no floating garbage."""
    result = normalize(1.0, unit_size=3.0)   # 0.333333... -> 0.333333
    decimal_str = ("%.10f" % result).rstrip("0")
    decimal_part = decimal_str.split(".", 1)[1] if "." in decimal_str else ""
    assert len(decimal_part) <= 6, (
        "result has more than 6 decimal places: %r" % result
    )


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_invalid_unit_size_raises():
    """unit_size <= 0 must raise ValueError -- callers must pass a sane base."""
    with pytest.raises(ValueError, match="unit_size"):
        normalize(100.0, unit_size=0.0)
    with pytest.raises(ValueError, match="unit_size"):
        normalize(100.0, unit_size=-50.0)


def test_negative_stake_raises():
    """Negative dollar stake is a caller bug -- raise ValueError."""
    with pytest.raises(ValueError, match="dollar_stake"):
        normalize(-10.0, unit_size=100)


# ---------------------------------------------------------------------------
# Default constants sanity
# ---------------------------------------------------------------------------

def test_default_unit_size_is_100():
    assert DEFAULT_UNIT_SIZE == 100.0


def test_unit_band_max_is_10():
    assert UNIT_BAND_MAX == 10.0


def test_defaults_used_when_no_args_except_stake():
    """normalize(dollar_stake) uses DEFAULT_UNIT_SIZE and UNIT_BAND_MAX."""
    result = normalize(500.0)
    expected = min(500.0 / DEFAULT_UNIT_SIZE, UNIT_BAND_MAX)
    assert math.isclose(result, expected, rel_tol=1e-9)
