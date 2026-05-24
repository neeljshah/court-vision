"""tests/test_96a_marginal_verification.py — Cycle 98e (loop 5).

Confirms the cycle-96a garbage-time haircut delivers a MARGINAL MAE
improvement (haircut ON vs haircut OFF) on the canonical 80/20 holdout
on top of the cycle-97a-fixed validator.

Why this exists:
The cycle 94a/95a probe measured the haircut delta against a baseline
that did NOT have the haircut wired (validator was buggy pre-97a).
Cycle 97a fixed the validator. These tests confirm that flipping
_APPLY_GARBAGE_HAIRCUT from True->False INCREASES PTS MAE by ~0.011
— proving the wire-in genuinely helps and isn't an artifact of the
old broken baseline.

Tests are skipped on systems missing the on-disk PTS model artifacts
(fresh checkout); CI on the maintainer's machine exercises them.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction import prop_pergame  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset, feature_columns, load_pergame_model,
)
from scripts.validate_adjustment import no_op, validate  # noqa: E402


# Cycle 96a reported numbers (probe_garbage_time_haircut_v2.py on the
# pre-97a-fixed validator baseline). The marginal verifier should reproduce
# these within ±0.002 because cycle 97a only made the baseline match the
# production path — the underlying marginal effect of the haircut on the
# real predictions does not depend on the validator code.
_96A_REPORTED_PTS_DELTA = 0.0117  # haircut REDUCES PTS MAE by this much


@pytest.fixture(scope="module")
def holdout_score_pair():
    """Score the canonical 80/20 holdout with haircut ON vs OFF, ONCE per
    test session. Yields (prod_mae_by_stat, abl_mae_by_stat)."""
    # Skip if the PTS model isn't on disk (fresh-checkout protection).
    pts_models = load_pergame_model("pts")
    if not pts_models:
        pytest.skip("PTS model artifacts missing on disk; this test only "
                    "runs in a trained environment.")

    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)

    original_flag = prop_pergame._APPLY_GARBAGE_HAIRCUT
    try:
        prop_pergame._APPLY_GARBAGE_HAIRCUT = True
        prod = {s: validate(no_op, holdout, X)[s]["baseline_mae"]
                for s in ("pts", "reb", "ast")}
        prop_pergame._APPLY_GARBAGE_HAIRCUT = False
        abl = {s: validate(no_op, holdout, X)[s]["baseline_mae"]
               for s in ("pts", "reb", "ast")}
    finally:
        prop_pergame._APPLY_GARBAGE_HAIRCUT = original_flag

    return prod, abl


def test_pts_with_haircut_matches_anchor(holdout_score_pair):
    """With haircut ON, PTS MAE matches the cycle-96a anchor (4.61)
    within tolerance."""
    prod, _ = holdout_score_pair
    # Anchor: cycle 96a reports PTS MAE 4.6104 with haircut wired in
    # (verify_production_mae quickstart says 4.61).
    assert prod["pts"] == pytest.approx(4.6104, abs=0.01), (
        f"PTS prod MAE drifted from anchor: got {prod['pts']:.4f}")


def test_pts_ablation_regresses_to_pre_haircut(holdout_score_pair):
    """With haircut OFF (flag flipped), PTS MAE worsens by ~0.011 —
    confirming the haircut wire-in is what's driving the cycle-96a
    PTS improvement."""
    prod, abl = holdout_score_pair
    delta = abl["pts"] - prod["pts"]  # positive = haircut helps
    assert delta >= 0.005, (
        f"Cycle 96a marginal benefit not observed: PTS abl-prod={delta:+.4f} "
        f"(expected >= 0.005). Wire-in may have regressed.")


def test_marginal_delta_matches_96a_reported(holdout_score_pair):
    """The measured PTS marginal (abl-prod) should reproduce cycle 96a's
    reported delta (-0.0117 on prod, so abl-prod = +0.0117) within ±0.002.
    Confirms the validator fix (97a) didn't drift the underlying effect."""
    prod, abl = holdout_score_pair
    measured = abl["pts"] - prod["pts"]
    assert measured == pytest.approx(_96A_REPORTED_PTS_DELTA, abs=0.002), (
        f"Marginal delta drifted from cycle 96a's report: "
        f"got {measured:+.4f}, expected {_96A_REPORTED_PTS_DELTA:+.4f} ± 0.002")
