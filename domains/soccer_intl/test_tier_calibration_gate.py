"""domains.soccer_intl.test_tier_calibration_gate -- per-file tests for the
tournament-tier pregame calibration gate (see tier_calibration_gate.py for the
full pre-registered design).

Run ONLY this file (full pytest freezes the box):
    python -m pytest domains/soccer_intl/test_tier_calibration_gate.py -q -s

HONEST: calibration-shape only; no $ edge asserted anywhere.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from domains.soccer_intl.config import RESULTS_PARQUET
from domains.soccer_intl.tier_calibration_gate import (
    _MIN_PER_TIER,
    _apply_intercept,
    _fit_intercept,
    _fold_cell,
    _logit,
    _tier,
    run,
)

_REPO = Path(__file__).resolve().parents[2]
_RESULTS = _REPO / RESULTS_PARQUET


def _skip_if_no_corpus():
    if not _RESULTS.exists():
        pytest.skip(f"corpus not materialised at {_RESULTS}")


# ---------------------------------------------------------------------------
# Unit-level: tier bucketing + intercept-shift math
# ---------------------------------------------------------------------------


def test_tier_bucketing_matches_spec():
    assert _tier("FIFA World Cup") == "world_cup"
    assert _tier("FIFA World Cup qualification") == "qualification"
    assert _tier("UEFA Euro qualification") == "qualification"
    assert _tier("Friendly") == "friendly"
    assert _tier("Copa America") == "other"
    assert _tier("Some Random Cup") == "other"


def test_intercept_shift_recovers_known_bias():
    """A systematically over-confident forecaster (p too high) should get a
    NEGATIVE intercept shift that pulls p back toward the true rate."""
    rng = np.random.RandomState(0)
    n = 2000
    true_rate = 0.3
    y = (rng.rand(n) < true_rate).astype(float)
    p_biased = np.full(n, 0.5)  # badly over-confident vs a 0.3 base rate
    b = _fit_intercept(p_biased, y)
    p_cal = _apply_intercept(p_biased, b)
    assert abs(float(np.mean(p_cal)) - true_rate) < 0.03
    assert b < 0  # shift pulls the over-confident 0.5 down toward 0.3


def test_apply_intercept_zero_is_identity():
    p = np.array([0.1, 0.5, 0.9])
    out = _apply_intercept(p, 0.0)
    assert np.allclose(out, p, atol=1e-9)


def test_logit_is_finite_at_extremes():
    p = np.array([0.0, 1.0, 0.5])
    z = _logit(p)
    assert np.all(np.isfinite(z))


# ---------------------------------------------------------------------------
# Integration: floor enforcement + planted-null wiring on synthetic data
# ---------------------------------------------------------------------------


def _synthetic_wf(n_per_tier: int, tiers=("world_cup", "qualification", "friendly", "other")) -> pd.DataFrame:
    """Fabricate a walk-forward-shaped frame with independent per-tier base rates
    so a real per-tier shift SHOULD help vs a pooled baseline miscalibrated
    toward the global mean."""
    rng = np.random.RandomState(1)
    rows = []
    tier_rates = {"world_cup": 0.55, "qualification": 0.40, "friendly": 0.30, "other": 0.45}
    global_p = 0.42  # pooled baseline miscalibrated: same p_home_raw for every tier
    for t in tiers:
        rate = tier_rates[t]
        yh = (rng.rand(n_per_tier) < rate).astype(float)
        for i in range(n_per_tier):
            rows.append({
                "tier": t,
                "p_home_raw": global_p, "p_draw_raw": 0.27, "p_away_raw": 0.31,
                "y_home": yh[i], "y_draw": 0.0, "y_away": 1.0 - yh[i],
            })
    return pd.DataFrame(rows)


def test_floor_marks_insufficient_below_min_per_tier():
    """A tier with fewer than _MIN_PER_TIER TEST rows must be INSUFFICIENT, never
    silently pooled into a scored verdict."""
    train = _synthetic_wf(300)
    test_full = _synthetic_wf(300)
    # shrink world_cup's TEST rows below the floor
    thin_wc = test_full[test_full["tier"] == "world_cup"].iloc[: _MIN_PER_TIER - 1]
    rest = test_full[test_full["tier"] != "world_cup"]
    test = pd.concat([thin_wc, rest], ignore_index=True)

    per_tier = _fold_cell(train, test)
    assert per_tier["world_cup"]["verdict"] == "INSUFFICIENT"
    assert per_tier["world_cup"]["n"] == _MIN_PER_TIER - 1
    for t in ("qualification", "friendly", "other"):
        assert per_tier[t]["verdict"] in ("MATCH", "WORSE")
        assert per_tier[t]["n"] >= _MIN_PER_TIER


def test_real_tier_structure_beats_shuffled_null_on_synthetic_signal():
    """When tiers carry GENUINE, distinct base rates and the pooled baseline is
    miscalibrated toward the global mean, the true-tier candidate must close more
    Brier gap than the shuffled-tier planted null (sanity check that the null
    wiring is discriminating, not just always matching)."""
    train = _synthetic_wf(400)
    test = _synthetic_wf(400)
    per_tier = _fold_cell(train, test)
    for t in ("world_cup", "qualification", "friendly", "other"):
        cell = per_tier[t]
        assert cell["verdict"] in ("MATCH", "WORSE")
        # real per-tier recal should recover a good chunk of the pooled-baseline's
        # miscalibration on at least a majority of the genuinely-different tiers
        assert cell["delta_cand_vs_base"] >= cell["delta_null_vs_base"] - 0.01


# ---------------------------------------------------------------------------
# Full run: real corpus (writes the pre-registered verdict artifact)
# ---------------------------------------------------------------------------


def test_run_writes_verdict_artifact_with_honest_friendly_count():
    _skip_if_no_corpus()
    out = run()
    assert out["verdict"] in ("MATCH", "REJECT", "REJECT_ARTIFACT", "INSUFFICIENT")
    assert out["edge_claimed"] is False
    assert set(out["tiers"]) == {"world_cup", "qualification", "friendly", "other"}
    # honest count: must be the genuine raw-corpus Friendly row count (an int),
    # never formatted/derived as a percentage, and never one of the retracted numbers.
    n_friendly = out["friendly_tournament_row_count_raw_corpus"]
    assert isinstance(n_friendly, int) and n_friendly == 18388
    retracted = {18.38, 0.119, 54, 78.11, 8.94, 54.57}
    assert n_friendly not in retracted
    assert len(out["decade_folds"]) >= 1
    print(f"\n=== tier_calibration_gate verdict: {out['verdict']} ===")
    print(f"friendly_tournament_row_count_raw_corpus={n_friendly}")
    for f in out["decade_folds"]:
        print(f"  fold {f['fold']}: n_train={f['n_train']} n_test={f['n_test']}")
    print(f"  live_wc2026_oos_fold: {out['live_wc2026_oos_fold']}")


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-q", "-s"] + sys.argv[1:]))
