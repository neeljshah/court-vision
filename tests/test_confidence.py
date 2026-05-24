"""Tests for src/prediction/confidence.py (cycle 77)."""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.confidence import (  # noqa: E402
    confidence_score, variance_score,
    _LINEUP_STATUS_WEIGHT, _LINEUP_CLS_WEIGHT, _INJURY_WEIGHT,
)


def test_variance_score_zero_width_returns_one():
    assert variance_score(20.0, 20.0, 20.0) == 1.0


def test_variance_score_tighter_interval_higher_score():
    """Narrower q10..q90 relative to q50 → higher score (more confident)."""
    tight = variance_score(18.0, 20.0, 22.0)   # CoV = 4/20 = 0.20
    wide = variance_score(10.0, 20.0, 30.0)    # CoV = 20/20 = 1.00
    assert tight > wide
    assert tight > 0.7
    assert wide < 0.4


def test_variance_score_returns_neutral_on_missing_inputs():
    assert variance_score(None, 20.0, 22.0) == 0.5
    assert variance_score(18.0, None, 22.0) == 0.5
    assert variance_score(18.0, 20.0, None) == 0.5


def test_confidence_score_perfect_signals_returns_high():
    """Tight interval + Confirmed Starter + PROBABLE → score ~85+."""
    score = confidence_score(
        q10=18.0, q50=20.0, q90=22.0,
        lineup_status="Confirmed",
        lineup_class="starter",
        injury_status="PROBABLE",
    )
    assert score >= 85


def test_confidence_score_bench_meaningfully_lower_than_starter():
    """BENCH classification should drop score noticeably vs a starter under
    identical model + injury conditions. Geometric mean dampens single-factor
    effects, but the gap should still be >= 15 points."""
    starter = confidence_score(
        q10=18.0, q50=20.0, q90=22.0,
        lineup_status="Confirmed", lineup_class="starter",
        injury_status="AVAILABLE",
    )
    bench = confidence_score(
        q10=18.0, q50=20.0, q90=22.0,
        lineup_status="Confirmed", lineup_class="bench",
        injury_status="AVAILABLE",
    )
    assert starter - bench >= 15


def test_confidence_score_OUT_drives_score_to_zero():
    """OUT injury status zeros the injury factor — geometric mean → ~0."""
    score = confidence_score(
        q10=18.0, q50=20.0, q90=22.0,
        lineup_status="Confirmed",
        lineup_class="starter",
        injury_status="OUT",
    )
    assert score == 0


def test_confidence_score_no_inputs_is_moderate():
    """All None → neutral defaults. Lineup_class defaults to 'unknown' (which
    weights 1.0 — treat as starter), so score lands in the 50-75 band."""
    score = confidence_score()
    assert 50 <= score <= 75


def test_confidence_score_wide_interval_drops_score():
    """Same lineup + injury, double-the-width interval → lower confidence."""
    tight = confidence_score(q10=18.0, q50=20.0, q90=22.0,
                              lineup_status="Confirmed", lineup_class="starter")
    wide = confidence_score(q10=10.0, q50=20.0, q90=30.0,
                             lineup_status="Confirmed", lineup_class="starter")
    assert tight > wide


def test_confidence_score_returns_int_in_range():
    """Always integer in [0, 100] regardless of inputs."""
    for tight in [(20, 20, 20), (10, 20, 50), (None, None, None)]:
        for cls in ("starter", "questionable", "bench", "unknown"):
            for inj in (None, "AVAILABLE", "QUESTIONABLE", "OUT"):
                s = confidence_score(*tight, lineup_class=cls, injury_status=inj)
                assert isinstance(s, int)
                assert 0 <= s <= 100


def test_weight_tables_have_expected_entries():
    """Lock in the design — change-detection if a band gets dropped."""
    assert "Confirmed" in _LINEUP_STATUS_WEIGHT
    assert "Expected" in _LINEUP_STATUS_WEIGHT
    assert _LINEUP_STATUS_WEIGHT["Confirmed"] > _LINEUP_STATUS_WEIGHT["Projected"]
    assert _LINEUP_CLS_WEIGHT["starter"] > _LINEUP_CLS_WEIGHT["questionable"]
    assert _LINEUP_CLS_WEIGHT["bench"] > _LINEUP_CLS_WEIGHT["no-game"]
    assert _INJURY_WEIGHT["AVAILABLE"] > _INJURY_WEIGHT["QUESTIONABLE"]
    assert _INJURY_WEIGHT["OUT"] == 0.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
