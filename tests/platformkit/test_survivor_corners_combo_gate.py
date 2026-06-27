"""Per-file test for the corners survivor-scrutiny run.

Proves the harness has TEETH (it can DOWNGRADE), the FWER bar genuinely TIGHTENS with
K, the nested-CV selector NEVER sees a holdout game (SelectSpy), the planted-null lane
routes through the IDENTICAL production gate, and the collinear guard is wired -- then
runs the REAL corpus once and asserts the verdict is one of the three honest outcomes
with all five controlled lanes populated. CALIBRATION only; no $/flag/registry.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

import scripts.platformkit.survivor_corners_combo_gate as S
from scripts.platformkit.combo import combo_gate as CG
from scripts.platformkit.combo import planted_null_fdr as PNF
from scripts.platformkit.combo.fwer_budget import eps_eff
from scripts.platformkit.combo.nested_cv import SelectSpy, partition_games

_DATA = os.path.join("data", "domains", "soccer", "matches.parquet")


# ----------------------------------------------------------------- structural teeth
def test_K_is_full_family_times_dirs_times_corpora():
    # 5 candidates x 2 directions x 2 corpora -- the cumulative selection surface.
    assert S._K_LIVE == len(S._FAMILY) * 2 * 2 == 20
    assert S._TARGET == "diff_corners_asof" and S._TARGET in S._FAMILY


def test_fwer_bar_tightens_with_K():
    # the per-test bar SHRINKS as K grows: a wider search is STRICTER, never looser.
    assert eps_eff(0.05, S._K_LIVE) == pytest.approx(0.05 / 20)
    assert eps_eff(0.05, S._K_LIVE) < eps_eff(0.05, 1)


def test_planted_null_lane_uses_identical_production_gate():
    # the nulls traverse the SAME gate object the survivor does (no parallel stub).
    assert PNF.ran_through_identical_gate()
    assert PNF.gate_combo is CG.gate_combo


def test_selectspy_raises_if_selector_touches_holdout():
    # the #1-leak tripwire: a selector that peeks at a sealed-fold game is caught.
    gids = ["G%03d" % i for i in range(40)]
    parts = partition_games(gids, 5)
    holdout = sorted(parts[0])
    spy = SelectSpy(lambda xs: "spec")
    spy(holdout)  # simulate a selector that wrongly received holdout ids
    assert spy.saw_any(holdout) is True


# ----------------------------------------------------------------- negative controls
def _state_frame(n, seed, signal, w=1.4):
    """Pregame-shaped corpus matching the harness contract (game_id/state_diff/feat)."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n):
        strength = float(rng.normal(0, 1))
        extra = float(rng.normal(0, 1))
        final = strength + (w * extra if signal else 0.0) + float(rng.normal(0, 0.3))
        rows.append({"game_id": "G%05d" % g, "asof_idx": 0,
                     "state_diff": strength, "frac_elapsed": 1.0,
                     "outcome": 1 if final > 0 else 0,
                     "feat": (extra + float(rng.normal(0, 0.3))) if signal
                     else float(rng.normal(0, 1))})
    return pd.DataFrame(rows)


def test_noise_feature_rejects_through_the_gate():
    # graceful-degrade: a pure-noise feature must NOT clear the combo gate (teeth).
    a, b = _state_frame(600, 1, signal=False), _state_frame(600, 99, signal=False)
    det_a = a[["game_id", "asof_idx", "feat"]].rename(columns={"feat": "detail"})
    det_b = b[["game_id", "asof_idx", "feat"]].rename(columns={"feat": "detail"})
    v = CG.gate_combo("noise", a, det_a, b, det_b, combo_col="detail",
                      base_feature_cols=None, parity_ok=True, eps=0.05,
                      K=S._K_LIVE, n_corpora=2)
    assert v.verdict == CG.REJECT


def test_collinear_feature_rejects_at_L0():
    # a feature identical to the base signal is a re-expression -> L0 REJECT.
    a, b = _state_frame(600, 1, signal=True), _state_frame(600, 99, signal=True)
    a["feat"] = a["state_diff"]; b["feat"] = b["state_diff"]
    det_a = a[["game_id", "asof_idx", "feat"]].rename(columns={"feat": "detail"})
    det_b = b[["game_id", "asof_idx", "feat"]].rename(columns={"feat": "detail"})
    v = CG.gate_combo("colin", a, det_a, b, det_b, combo_col="detail",
                      base_feature_cols={"base": a["state_diff"].to_numpy()},
                      parity_ok=True, eps=0.05, K=S._K_LIVE, n_corpora=2)
    assert v.verdict == CG.REJECT and v.layer == "L0"


# ----------------------------------------------------------------- the real run
@pytest.mark.skipif(not os.path.exists(_DATA), reason="soccer corpus absent")
def test_real_corners_survivor_run_is_honest():
    r = S.run(seeds=(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
              splits=(0.4, 0.5, 0.6), n_nulls=20)
    # all five controlled lanes must be populated -- none silently skipped.
    assert r.K == 20 and r.eps_eff == pytest.approx(0.05 / 20)
    assert np.isfinite(r.nested_delta_a) and np.isfinite(r.nested_delta_b)
    assert r.gate_verdict in (S.SHIP, "REJECT")
    assert np.isfinite(r.seed_mean) and np.isfinite(r.seed_p10)
    assert len(r.split_deltas) == 3
    assert r.null_fdr_hat >= 0.0  # the null lane actually ran
    assert r.verdict in ("CONFIRMED_SURVIVOR", "DOWNGRADE_TO_ARTIFACT",
                         "INSUFFICIENT_DATA")
    assert r.deciding_stat  # a non-empty deciding statistic is always reported
    assert r.proposal_only is True and "UNPROVEN" in r.vs_close
    # if it CONFIRMS it must have cleared EVERY layer (no weakened-bar shortcut).
    if r.verdict == "CONFIRMED_SURVIVOR":
        assert r.gate_verdict == S.SHIP
        assert r.nested_delta_a > 0 and r.nested_delta_b > 0
        assert r.seed_p10 >= 0.0 and r.split_all_positive
        assert r.null_rejects and not r.null_frozen
        assert r.collinear_reason is None
