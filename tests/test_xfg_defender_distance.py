"""
test_xfg_defender_distance.py -- Tests for the xFG defender-distance adjustment (PRED-06).

Acceptance criterion: xFG applies the canonical defender-distance → multiplier
curve from CANONICAL_VALUES.md; a null/sentinel distance falls back to ×1.0;
each distance band is covered.
"""

from __future__ import annotations

import os
import sys

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.xfg_model import defender_distance_multiplier  # noqa: E402


# ── canonical bands ───────────────────────────────────────────────────────────

def test_heavily_contested_band_0_to_2ft():
    """0–2 ft (heavy contest) -> ×0.82."""
    assert defender_distance_multiplier(0.0) == 0.82
    assert defender_distance_multiplier(1.5) == 0.82
    assert defender_distance_multiplier(2.0) == 0.82


def test_contested_band_3_to_5ft():
    """3–5 ft (contested) -> ×0.91."""
    assert defender_distance_multiplier(3.0) == 0.91
    assert defender_distance_multiplier(5.0) == 0.91


def test_lightly_contested_band_6_to_10ft():
    """6–10 ft (lightly contested) -> ×0.99."""
    assert defender_distance_multiplier(6.0) == 0.99
    assert defender_distance_multiplier(10.0) == 0.99


def test_open_look_band_over_10ft():
    """10+ ft (open) -> ×1.05."""
    assert defender_distance_multiplier(11.0) == 1.05
    assert defender_distance_multiplier(25.0) == 1.05


# ── tighter contest lowers xFG, open raises it ───────────────────────────────

def test_multiplier_is_monotonic_in_distance():
    """More space never lowers the multiplier."""
    mults = [defender_distance_multiplier(d) for d in (1, 4, 8, 15)]
    assert mults == sorted(mults)
    assert mults[0] < 1.0 < mults[-1]


# ── null / sentinel fallback ─────────────────────────────────────────────────

def test_none_distance_falls_back_to_neutral():
    """A missing defender distance leaves xFG unchanged (×1.0)."""
    assert defender_distance_multiplier(None) == 1.0


def test_isolation_sentinel_treated_as_unknown():
    """The 200.0 isolation sentinel (ISSUE-022) is treated as unknown -> ×1.0."""
    assert defender_distance_multiplier(200.0) == 1.0


def test_nan_and_negative_fall_back_to_neutral():
    """NaN and negative distances are neutral, not crashes."""
    assert defender_distance_multiplier(float("nan")) == 1.0
    assert defender_distance_multiplier(-3.0) == 1.0
    assert defender_distance_multiplier("not a number") == 1.0


def test_adjustment_applied_to_a_base_probability():
    """Applying the multiplier to a base xFG keeps it a valid probability."""
    base = 0.55
    contested = base * defender_distance_multiplier(1.0)   # ×0.82
    open_look = base * defender_distance_multiplier(20.0)  # ×1.05
    assert contested < base < open_look
    assert 0.0 <= contested <= 1.0 and 0.0 <= open_look <= 1.0
    assert np.isclose(contested, 0.55 * 0.82)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
