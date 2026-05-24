"""tests/test_outlier_uplift.py — Cycle 98c (loop 5).

Outlier-uplift adjustment factory tests:
  1. uplift_factor=0.0 -> zero MAE delta on every stat (no-op)
  2. uplift_factor=0.05 + outlier_prior > threshold -> pred scales
  3. outlier_prior < threshold -> unchanged
  4. Outlier definition on synthetic L20 data correctly identifies top-decile
  5. Player with no L20 history -> graceful default (no uplift applied
     because base prior 0.10 falls below default 0.15 threshold)
  6. Statistical: across synthetic holdout, ~15% of rows should trigger
     uplift at threshold 0.15
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.probe_outlier_uplift import (  # noqa: E402
    _UPLIFT_STATS,
    compute_outlier_prior,
    make_outlier_uplift,
)


# ── fixtures ─────────────────────────────────────────────────────────────────

def _l20(pid, date_iso, *, blk_q75=1.0, blk_q90=2.0, fg3m_q75=2.0, fg3m_q90=3.0, n=20):
    return {
        (pid, date_iso): {
            "blk":  {"q75": blk_q75, "q90": blk_q90, "n": float(n)},
            "fg3m": {"q75": fg3m_q75, "q90": fg3m_q90, "n": float(n)},
        }
    }


# ── 1. no-op test ────────────────────────────────────────────────────────────

def test_uplift_zero_is_exact_noop_on_all_stats():
    """uplift_factor=0.0 must produce IDENTICAL floats on every stat."""
    l20 = _l20(123, "2025-04-01")
    fn = make_outlier_uplift(uplift_factor=0.0, prob_threshold=0.15,
                              l20_lookup=l20)
    pred = np.array([0.5, 1.0, 2.5, 1.5], dtype=float)
    rows = [
        # Hot-streak center (would trigger if uplift > 0)
        {"player_id": 123, "date": "2025-04-01", "l5_blk": 5.0, "l5_fg3m": 5.0},
        {"player_id": 123, "date": "2025-04-01", "l5_blk": 0.0, "l5_fg3m": 0.0},
        {"player_id": 123, "date": "2025-04-01", "l5_blk": 3.0, "l5_fg3m": 3.0},
        {"player_id": 123, "date": "2025-04-01", "l5_blk": 1.0, "l5_fg3m": 1.0},
    ]
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        out = fn(pred, rows, stat)
        np.testing.assert_array_equal(
            out, pred,
            err_msg=f"stat={stat} factor=0.0 must be identity"
        )


# ── 2. scaling fires when prior > threshold ──────────────────────────────────

def test_uplift_scales_when_outlier_prior_above_threshold():
    """l5 > q90 -> prior=0.25 > 0.15 threshold -> pred *= 1.05."""
    l20 = _l20(42, "2025-04-15", blk_q75=1.0, blk_q90=2.0)
    fn = make_outlier_uplift(uplift_factor=0.05, prob_threshold=0.15,
                              l20_lookup=l20)
    # l5_blk=3.0 is above q90=2.0 -> prior=0.10+0.10+0.05=0.25 > 0.15
    rows = [{"player_id": 42, "date": "2025-04-15", "l5_blk": 3.0}]
    pred = np.array([1.0], dtype=float)
    out = fn(pred, rows, "blk")
    np.testing.assert_allclose(out, np.array([1.05]), rtol=0, atol=1e-12)


# ── 3. below threshold -> unchanged ──────────────────────────────────────────

def test_uplift_does_not_fire_when_prior_below_threshold():
    """l5 < q75 -> prior=0.10 < 0.15 threshold -> pred unchanged."""
    l20 = _l20(42, "2025-04-15", blk_q75=1.5, blk_q90=2.5)
    fn = make_outlier_uplift(uplift_factor=0.10, prob_threshold=0.15,
                              l20_lookup=l20)
    rows = [{"player_id": 42, "date": "2025-04-15", "l5_blk": 0.5}]
    pred = np.array([0.8], dtype=float)
    out = fn(pred, rows, "blk")
    np.testing.assert_array_equal(out, pred)


# ── 4. outlier prior correctly identifies top-decile on synthetic L20 ────────

def test_outlier_prior_identifies_top_decile_on_synthetic_distribution():
    """On a uniform L20 distribution, q75 and q90 thresholds work as expected."""
    # Player with very high L20 q90: a low l5 should give base prior only;
    # an l5 above q90 should give the full bump.
    l20 = _l20(7, "2025-05-01", blk_q75=2.0, blk_q90=4.0)
    row_low  = {"player_id": 7, "date": "2025-05-01", "l5_blk": 1.0}
    row_mid  = {"player_id": 7, "date": "2025-05-01", "l5_blk": 3.0}  # above q75 only
    row_high = {"player_id": 7, "date": "2025-05-01", "l5_blk": 5.0}  # above q90 too

    assert compute_outlier_prior(row_low, "blk", l20) == pytest.approx(0.10)
    assert compute_outlier_prior(row_mid, "blk", l20) == pytest.approx(0.20)
    assert compute_outlier_prior(row_high, "blk", l20) == pytest.approx(0.25)

    # Cap at 0.30 -- but with current bumps (+0.10, +0.05) max is 0.25
    # so the cap isn't tested here. Test cap explicitly via custom prior bumps
    # would require deeper hook; the implementation's min(prior, 0.30) is
    # exercised by the design.


# ── 5. player with no L20 history -> graceful default ────────────────────────

def test_no_history_player_gets_base_prior_no_uplift():
    """When (pid, date) absent from L20 lookup, prior=0.10 -> < 0.15 threshold."""
    l20: dict = {}  # empty lookup
    fn = make_outlier_uplift(uplift_factor=0.10, prob_threshold=0.15,
                              l20_lookup=l20)
    rows = [
        {"player_id": 999, "date": "2025-04-01", "l5_blk": 10.0},
        # missing player_id entirely
        {"date": "2025-04-01", "l5_blk": 10.0},
        # missing date
        {"player_id": 999, "l5_blk": 10.0},
    ]
    pred = np.array([2.0, 2.0, 2.0], dtype=float)
    out = fn(pred, rows, "blk")
    # No L20 -> base prior 0.10 -> below 0.15 -> no uplift -> identity.
    np.testing.assert_array_equal(out, pred)

    # Direct prior check
    assert compute_outlier_prior(rows[0], "blk", l20) == pytest.approx(0.10)
    assert compute_outlier_prior(rows[1], "blk", l20) == pytest.approx(0.10)
    assert compute_outlier_prior(rows[2], "blk", l20) == pytest.approx(0.10)


# ── 6. statistical sanity: ~15% of holdout should trigger at threshold 0.15 ──

def test_uplift_fires_on_realistic_fraction_of_synthetic_holdout():
    """With a realistic mix of hot/cold/neutral players, the trigger fraction
    should land in a sane band [5%, 50%]. Cycle 96e finding: outlier games
    are ~10% by definition; recent-form bump should push a similar minority
    above 0.15 threshold without flooding (which would suggest a bad prior).
    """
    rng = np.random.default_rng(42)
    n = 500
    l20: dict = {}
    rows = []
    for i in range(n):
        pid = 1000 + i
        date_iso = f"2025-{(i % 12) + 1:02d}-15"
        # Random player baselines: q75 in [0.5, 2.0], q90 = q75 + uniform(0.5, 1.5)
        q75 = float(rng.uniform(0.5, 2.0))
        q90 = q75 + float(rng.uniform(0.5, 1.5))
        l20[(pid, date_iso)] = {
            "blk":  {"q75": q75, "q90": q90, "n": 20.0},
            "fg3m": {"q75": q75, "q90": q90, "n": 20.0},
        }
        # l5 sampled from N(q75 * 0.7, q75 * 0.6) — most players cold/neutral,
        # ~20-30% recently hot.
        l5 = max(0.0, float(rng.normal(q75 * 0.7, q75 * 0.6)))
        rows.append({"player_id": pid, "date": date_iso, "l5_blk": l5})

    priors = np.array([compute_outlier_prior(r, "blk", l20) for r in rows])
    frac_above = float(np.mean(priors > 0.15))
    # Sanity band: enough rows to drive an MAE shift, but not so many it's
    # a global rescale.
    assert 0.05 <= frac_above <= 0.50, (
        f"frac_above_0.15 = {frac_above:.3f} out of sane [0.05, 0.50] band"
    )


# ── bonus: target_stats gating (single-stat probe discipline) ────────────────

def test_non_target_stats_are_strict_noop_even_when_prior_triggers():
    """Even with prior triggering, target_stats=(blk, fg3m) gates ALL other stats."""
    l20 = _l20(42, "2025-04-15", blk_q75=1.0, blk_q90=2.0,
                fg3m_q75=1.0, fg3m_q90=2.0)
    fn = make_outlier_uplift(uplift_factor=0.10, prob_threshold=0.15,
                              l20_lookup=l20,
                              target_stats=_UPLIFT_STATS)
    rows = [{"player_id": 42, "date": "2025-04-15",
             "l5_blk": 5.0, "l5_fg3m": 5.0}]
    pred = np.array([3.0], dtype=float)
    for stat in ("pts", "reb", "ast", "stl", "tov"):
        out = fn(pred, rows, stat)
        np.testing.assert_array_equal(
            out, pred,
            err_msg=f"stat={stat} not in target_stats must be no-op"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
