"""test_q4_foul_forecast_v2.py -- cycle 97e (loop 5).

Validates the NNLS-fit + gated + round-down v2 Q4 PF forecast.
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.q4_foul_forecast_v2 import (  # noqa: E402
    FEATURE_NAMES,
    GATE_MIN_PF,
    GATE_MIN_Q3,
    build_feature_row,
    build_training_data,
    cross_val_mae,
    fit_coefficients,
    forecast_q4_pf_addition_v2,
    forecasted_endgame_pf_v2,
    passes_gate,
)


def test_synthetic_nnls_recovers_known_beta():
    """Train on synthetic data with known beta; fit must recover within 10%."""
    import random
    rng = random.Random(0)
    true_beta = [0.20, 0.30, 0.05, 0.40, 0.01]  # one entry per feature
    assert len(true_beta) == len(FEATURE_NAMES)
    n = 500
    feature_rows = []
    targets = []
    for _ in range(n):
        feats = [
            float(rng.randint(2, 5)),      # pf_through_q3
            float(rng.randint(0, 3)),      # q3_pf
            rng.uniform(6.0, 12.0),        # min_q3
            float(rng.randint(0, 1)),      # is_center
            rng.uniform(15.0, 25.0),       # opp_foul_rate_l5
        ]
        y = sum(b * x for b, x in zip(true_beta, feats))
        # tiny gaussian noise
        y += rng.gauss(0.0, 0.05)
        feature_rows.append(feats)
        targets.append(max(0.0, y))
    coef = fit_coefficients(feature_rows, targets)
    for i, (got, want) in enumerate(zip(coef, true_beta)):
        # allow 10% relative OR 0.05 absolute tolerance
        tol = max(0.10 * abs(want), 0.05)
        assert abs(got - want) <= tol, (
            f"feature {FEATURE_NAMES[i]}: recovered {got:.4f} vs true "
            f"{want:.4f} (tol {tol:.4f})"
        )


def test_no_op_at_gate_floor():
    """At the GATE floor (pf=2, min_q3=6) the forecasted endgame pf must
    round DOWN to match the snapshot pf -- no behavior change at the edge.
    This guarantees that crossing the gate is a smooth no-op until the
    forecast crosses a full integer band.
    """
    # Use the cached coefficients fit from the retro corpus.
    end_pf = forecasted_endgame_pf_v2(
        pf_through_q3=2, q3_pf=0, min_q3=6.0, position_proxy="Guard",
        opp_foul_rate_l5=20.0,
    )
    assert end_pf == 2, (
        f"expected 2 at gate floor (round-down truncation), got {end_pf}"
    )


def test_gate_blocks_obvious_cases():
    """Gate must return False for both low-foul and low-minutes cases."""
    # Low foul state: pf=1 with plenty of minutes -- not in trouble.
    assert not passes_gate(1, 24.0), "pf=1 should not pass gate"
    # Low minutes: high pf but insufficient sample -- forecast too noisy.
    assert not passes_gate(4, 2.0), "min_q3=2 should not pass gate"
    # Pass case (positive control).
    assert passes_gate(GATE_MIN_PF, GATE_MIN_Q3), (
        "gate floors should pass exactly at the boundary"
    )
    # Below either floor should fail.
    assert not passes_gate(GATE_MIN_PF - 1, GATE_MIN_Q3)
    assert not passes_gate(GATE_MIN_PF, GATE_MIN_Q3 - 0.01)


def test_zero_for_season_start_player():
    """A player with no Q3 minutes (e.g. game start, no L5 stats yet)
    must get 0 additional fouls -- the gate must block."""
    # min_q3 = 0 and pf = 0 -- the canonical "we know nothing" case.
    pred = forecast_q4_pf_addition_v2(
        pf_through_q3=0, q3_pf=0, min_q3=0.0, position_proxy=None,
        opp_foul_rate_l5=None,
    )
    assert pred == 0.0, f"expected 0 additional fouls, got {pred}"
    end_pf = forecasted_endgame_pf_v2(
        pf_through_q3=0, q3_pf=0, min_q3=0.0, position_proxy=None,
    )
    assert end_pf == 0, f"expected endgame pf=0 for no-info player, got {end_pf}"


def test_retro_bias_below_half_of_v1():
    """Bias on the retro corpus must be <= 0.20 PF (cycle 96c was 0.38 ->
    failure). v2 must halve that to clear the gate."""
    X, y, _ = build_training_data()
    if not X:
        # Skip if parquet missing in the test env -- treat as informational.
        return
    coef = fit_coefficients(X, y)
    preds = [sum(c * v for c, v in zip(coef, row)) for row in X]
    bias = sum(p - a for p, a in zip(preds, y)) / len(y)
    assert abs(bias) <= 0.20, (
        f"forecast bias |{bias:+.4f}| > 0.20 (v1 was +0.38, that was the failure)"
    )


def test_cv_mae_competitive_with_v1():
    """Cross-validated Q4 PF MAE on the retro must be < 0.80
    (v1 was 0.7629 on the un-gated set; gated set should be similar
    or better since the signal-to-noise improves)."""
    X, y, _ = build_training_data()
    if not X:
        return
    cv = cross_val_mae(X, y, k=5, seed=0)
    assert cv == cv, "CV MAE returned NaN"  # NaN check
    assert cv < 0.80, f"CV MAE {cv:.4f} >= 0.80 ship gate"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
