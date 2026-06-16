"""Per-file pytest for the N3 in-game blend (synthetic-validated PATTERN ONLY).

Run ONLY as:
    python -m pytest domains/basketball_nba/tests/test_ingame_blend.py -q

NEVER run the full suite (it freezes the box). These tests prove the WIRING +
the honest-discipline flags on synthetic data; they do NOT assert a real-corpus
win (that is a HUMAN-RUN step, flagged pending everywhere).
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.eval_gate.dm_test import DMResult
from domains.basketball_nba.ingame_blend_prior import derive_p0, proj_margin
from domains.basketball_nba.ingame_blend_plive import (
    PLIVE_FEATS,
    build_state_features,
    fit_plive,
    predict_plive,
    sec_remaining,
)
from domains.basketball_nba.ingame_blend_surface import (
    blend,
    exp_smooth,
    fit_surface_on_season,
    garbage_clamp,
    grid_monotone_score,
)
from domains.basketball_nba.ingame_blend_eval import (
    REAL_OOS_VALIDATION_PENDING,
    brier,
    dm_blend_vs_pregame,
    make_synthetic_season,
    run_synthetic_proof,
)


# --------------------------------------------------------------------------- P0
def test_derive_p0_monotone_with_margin():
    base_h = np.full(2000, 110.0)
    p_lo = derive_p0(home_total=base_h, away_total=np.full(2000, 120.0))
    p_mid = derive_p0(home_total=base_h, away_total=np.full(2000, 110.0))
    rng = np.random.default_rng(0)
    h = rng.normal(115, 10, 4000)
    a = rng.normal(108, 10, 4000)
    p_hi = derive_p0(home_total=h, away_total=a)
    assert 0.0 <= p_lo <= p_mid <= p_hi <= 1.0
    assert p_lo < 0.05 and p_mid == pytest.approx(0.5, abs=1e-9) and p_hi > 0.5


def test_derive_p0_from_sim_result_object():
    class _Res:
        home_total = np.array([100.0, 105.0, 110.0])
        away_total = np.array([99.0, 99.0, 99.0])
    assert derive_p0(_Res()) == pytest.approx(1.0)
    assert proj_margin(_Res().home_total, _Res().away_total) == pytest.approx(6.0)


# --------------------------------------------------------------------------- blend bounds
def test_blend_bounds_and_endpoints():
    assert blend(0.3, 0.9, 0.0) == pytest.approx(0.3)   # w=0 -> P0
    assert blend(0.3, 0.9, 1.0) == pytest.approx(0.9)   # w=1 -> P_live
    for w in np.linspace(0, 1, 11):
        b = blend(0.2, 0.8, float(w))
        assert 0.0 <= b <= 1.0


# --------------------------------------------------------------------------- garbage clamp
def test_garbage_clamp_only_late_blowout():
    # late + blowout -> pushed to the deterministic extreme
    assert garbage_clamp(0.6, margin_abs=25, sec_remaining=30, leader_is_home=True) == 0.98
    assert garbage_clamp(0.6, margin_abs=25, sec_remaining=30, leader_is_home=False) == 0.02
    # early or close -> unchanged
    assert garbage_clamp(0.6, margin_abs=25, sec_remaining=900) == pytest.approx(0.6)
    assert garbage_clamp(0.6, margin_abs=4, sec_remaining=30) == pytest.approx(0.6)


# --------------------------------------------------------------------------- EMA causal
def test_exp_smooth_causal():
    seq = [0.0, 1.0, 1.0, 1.0]
    # prefix smoothing: each point depends only on past + present, never future
    s2 = exp_smooth(seq[:2], alpha=0.5)
    s3 = exp_smooth(seq[:3], alpha=0.5)
    assert s2 == pytest.approx(0.5)
    assert s3 == pytest.approx(0.75)
    assert exp_smooth([], alpha=0.5) == 0.0


# --------------------------------------------------------------------------- features
def test_sec_remaining_and_features():
    assert sec_remaining(1, 720.0) == pytest.approx(2880.0)
    assert sec_remaining(4, 0.0) == pytest.approx(0.0)
    st = {
        "period": 4, "clock_s": 300.0, "home_score": 90, "away_score": 85,
        "players": {
            "h1": {"team": "HOM", "pf": 5}, "h2": {"team": "HOM", "pf": 1},
            "a1": {"team": "AWY", "pf": 2},
        },
        "home_bonus": True, "away_bonus": False,
    }
    f = build_state_features(st, "HOM", "AWY")
    assert set(PLIVE_FEATS).issubset(f)
    assert f["score_diff"] == 5 and f["foul_diff"] == -1 and f["bonus"] == 1


# --------------------------------------------------------------------------- P_live fit/predict
def test_plive_fit_predict_bounds():
    rows, labels = [], []
    rng = np.random.default_rng(3)
    for _ in range(400):
        sd = float(rng.normal(0, 10))
        rows.append({"score_diff": sd, "sec_remaining": float(rng.uniform(0, 2880)),
                     "foul_diff": 0.0, "bonus": 0.0,
                     "time_pressure": sd / 600.0})
        labels.append(1.0 if sd + rng.normal(0, 5) > 0 else 0.0)
    model = fit_plive(rows, labels)
    p = predict_plive(model, rows[0])
    assert 0.0 <= p <= 1.0


# --------------------------------------------------------------------------- weight surface
def test_fit_weight_surface_in_sample_le_oos_and_monotone():
    a = make_synthetic_season("synthA", seed=11)
    b = make_synthetic_season("synthB", seed=29)
    surf = fit_surface_on_season(a)
    from scripts.platformkit.eval_gate.ingame_blend import blended_predictions
    in_b = brier(blended_predictions(a, surf), [s["outcome"] for s in a])
    oos_b = brier(blended_predictions(b, surf), [s["outcome"] for s in b])
    # in-sample fit cannot be worse than OOS (Brier-minimizing per cell)
    assert in_b <= oos_b + 1e-9
    # coarse monotone-ish sanity on the fitted surface
    assert grid_monotone_score(surf) >= 0.5


# --------------------------------------------------------------------------- DM wrapper
def test_dm_wrapper_returns_dmresult():
    b = make_synthetic_season("synthB", seed=29)
    from scripts.platformkit.eval_gate.ingame_blend import blended_predictions
    surf = fit_surface_on_season(make_synthetic_season("synthA", seed=11))
    res = dm_blend_vs_pregame(b, blended_predictions(b, surf))
    assert isinstance(res, DMResult)
    assert res.n_clusters >= 1


# --------------------------------------------------------------------------- honesty flags
def test_harness_emits_validation_pending_on_synthetic():
    assert REAL_OOS_VALIDATION_PENDING is True
    proof = run_synthetic_proof(write=False)
    assert proof["real_oos_validation_pending"] is True
    assert proof["corpus"] == "SYNTHETIC"
    assert proof["edge_claimed"] is False
    for run in proof["runs"]:
        assert run["validation_pending"] is True
        assert run["corpus"] == "SYNTHETIC"
        assert run["edge_claimed"] is False
        assert "overfit_gap_ok" in run
        assert run["honest_verdict"] in (
            "blend_adds_calibration", "market_efficient_or_no_gain__SUCCESS")
