"""Negative control (e): a real synthetic combo SHIPs; noise + single-negative-fold REJECT.

Also asserts the DM clustered-by-game p is LARGER than the naive iid p (the cluster
correction is load-bearing -- it does not manufacture significance).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.combo.combo_gate import SHIP, REJECT, gate_combo
from scripts.platformkit.eval_gate.dm_test import diebold_mariano


def _build(n_games, ticks, seed, signal=True, w=1.4):
    """Two-corpus base + detail: detail carries a leak-free factor (signal) or noise."""
    rng = np.random.default_rng(seed)
    rows, drows = [], []
    for g in range(n_games):
        strength = float(rng.normal(0, 1))
        extra = float(rng.normal(0, 1))
        final = strength + w * extra + float(rng.normal(0, 0.3))
        outcome = 1 if final > 0 else 0
        for t in range(ticks):
            frac = (t + 1) / ticks
            sd = strength * frac * 10 + float(rng.normal(0, 1))
            rows.append({"game_id": "G%03d" % g, "asof_idx": t, "state_diff": sd,
                         "frac_elapsed": frac, "outcome": outcome})
            d = (extra + float(rng.normal(0, 0.3))) if signal else float(rng.normal(0, 1))
            drows.append({"game_id": "G%03d" % g, "asof_idx": t, "detail": d})
    return pd.DataFrame(rows), pd.DataFrame(drows)


def test_real_combo_ships():
    ba, da = _build(150, 8, 1, signal=True)
    bb, db = _build(150, 8, 202, signal=True)
    v = gate_combo("spec_real", ba, da, bb, db, combo_col="detail",
                   base_feature_cols=None, parity_ok=True, eps=0.05, K=1, n_corpora=2)
    assert v.verdict == SHIP, v.to_dict()
    assert v.detail["cross_verdict"] == "REPLICATED"


def test_noise_combo_rejects():
    ba, da = _build(150, 8, 1, signal=False)
    bb, db = _build(150, 8, 202, signal=False)
    v = gate_combo("spec_noise", ba, da, bb, db, combo_col="detail",
                   base_feature_cols=None, parity_ok=True, eps=0.05, K=1, n_corpora=2)
    assert v.verdict == REJECT
    assert v.layer in ("L4", "L5")


def test_single_negative_fold_rejects():
    """A combo that wins ONE direction only -> PARTIAL inside the gate -> hard REJECT.

    Corpus A carries the real factor; corpus B is pure noise -> only one direction can
    win, so the both-directions decide() returns PARTIAL/REJECT, never SHIP.
    """
    ba, da = _build(150, 8, 1, signal=True)
    bb, db = _build(150, 8, 202, signal=False)
    v = gate_combo("spec_onesided", ba, da, bb, db, combo_col="detail",
                   base_feature_cols=None, parity_ok=True, eps=0.05, K=1, n_corpora=2)
    assert v.verdict == REJECT


def test_parity_break_rejects_at_L0():
    ba, da = _build(150, 8, 1, signal=True)
    bb, db = _build(150, 8, 202, signal=True)
    v = gate_combo("spec", ba, da, bb, db, combo_col="detail", parity_ok=False,
                   eps=0.05, K=1, n_corpora=2)
    assert v.verdict == REJECT and v.layer == "L0"


def test_collinear_combo_rejects_at_L0():
    ba, da = _build(150, 8, 1, signal=True)
    bb, db = _build(150, 8, 202, signal=True)
    # base feature == the combo column itself -> re-expression
    base_feats = {"shipped": da["detail"].to_numpy()}
    v = gate_combo("spec", ba, da, bb, db, combo_col="detail",
                   base_feature_cols=base_feats, parity_ok=True, eps=0.05, K=1,
                   n_corpora=2)
    assert v.verdict == REJECT and v.layer == "L0"
    assert v.reason.startswith("collinear_with_base")


def test_frozen_family_does_not_gate():
    ba, da = _build(150, 8, 1, signal=True)
    bb, db = _build(150, 8, 202, signal=True)
    v = gate_combo("spec", ba, da, bb, db, combo_col="detail", parity_ok=True,
                   eps=0.05, K=1, n_corpora=2, family_frozen=True)
    assert v.verdict == REJECT and v.layer == "FDR"


def test_clustered_p_exceeds_naive_p():
    """DM clustered by game_id gives a LARGER p than the naive iid SE (R6).

    Many states per game are correlated; the cluster-sum estimator does NOT manufacture
    significance -- the clustered p must be >= the naive p on the same loss differences.
    """
    rng = np.random.default_rng(3)
    n_games, ticks = 30, 40
    d, cl = [], []
    for g in range(n_games):
        # a per-game tilt makes within-game d's correlated; the iid SE ignores this and
        # runs too narrow, while the cluster-sum SE widens it (the ~3x bug this fixes).
        tilt = float(rng.normal(0.006, 0.08))
        for _ in range(ticks):
            d.append(tilt + float(rng.normal(0, 0.03)))
            cl.append(g)
    clustered = diebold_mariano(d, cl).p_value
    naive = diebold_mariano(d, list(range(len(d)))).p_value  # each obs its own cluster
    # The iid SE crushes p toward 0 (fake significance); clustering by game widens the SE
    # so the clustered p is strictly LARGER -- it does NOT manufacture significance (R6).
    assert clustered > naive, (clustered, naive)
    assert clustered > 0.01, clustered      # clustered p is a non-trivial, honest value
    assert naive < clustered                # the inflation gap is real
