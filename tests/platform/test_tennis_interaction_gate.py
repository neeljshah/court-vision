"""tests.platform.test_tennis_interaction_gate -- Family A1-T unit tests (synthetic).

The real gate run is a __main__ guard (domains.tennis.interaction_gate); this
file exercises the pure math functions on canned frames so it never touches
the real parquet corpora. ASCII; per-file only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.tennis import interaction_gate as g
from domains.tennis import interaction_gate_math as gm
from scripts.platformkit.combo import stack_fit as sf


def _synthetic_frame(n: int, seed: int, surface_coverage: float = 1.0) -> pd.DataFrame:
    """A canned frame with the SAME columns build_corpus_frame produces."""
    rng = np.random.default_rng(seed)
    p_elo = np.clip(rng.normal(0.5, 0.12, size=n), 0.03, 0.97)
    surfaces = rng.choice(["Hard", "Clay", "Grass"], size=n)
    blended = rng.normal(0.0, 0.05, size=n)
    p1_hold = 0.65 + rng.normal(0.0, 0.05, size=n)
    p2_hold = p1_hold - blended
    p1_hard = p1_hold + rng.normal(0.0, 0.02, size=n)
    p2_hard = p2_hold + rng.normal(0.0, 0.02, size=n)
    p1_clay = p1_hold + rng.normal(0.0, 0.02, size=n)
    p2_clay = p2_hold + rng.normal(0.0, 0.02, size=n)
    p1_grass = p1_hold + rng.normal(0.0, 0.02, size=n)
    p2_grass = p2_hold + rng.normal(0.0, 0.02, size=n)
    n_prior = np.full(n, 20)
    if surface_coverage < 1.0:
        mask = rng.uniform(0, 1, size=n) > surface_coverage
        for arr in (p1_hard, p2_hard, p1_clay, p2_clay, p1_grass, p2_grass):
            arr[mask] = np.nan
    y = (rng.uniform(0, 1, size=n) < p_elo).astype(float)
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "date": pd.date_range("2015-01-01", periods=n, freq="D"),
        "target_p1_win": y,
        "p_elo": p_elo,
        "p_close": np.clip(p_elo + rng.normal(0.0, 0.02, size=n), 0.03, 0.97),
        "surface": surfaces,
        "p1_n_prior": n_prior, "p2_n_prior": n_prior,
        "p1_hold_pct_asof": p1_hold, "p2_hold_pct_asof": p2_hold,
        "p1_hold_pct_hard_asof": p1_hard, "p2_hold_pct_hard_asof": p2_hard,
        "p1_hold_pct_clay_asof": p1_clay, "p2_hold_pct_clay_asof": p2_clay,
        "p1_hold_pct_grass_asof": p1_grass, "p2_hold_pct_grass_asof": p2_grass,
    })


def test_t1_added_raw_shape_and_fallback_on_carpet_unknown():
    df = _synthetic_frame(200, seed=1)
    df.loc[0, "surface"] = "Carpet"
    added = gm.t1_added_raw(df)
    assert added.shape == (200, 2)
    assert not np.isfinite(added[0]).any()  # Carpet row -> no surface hold cols -> NaN


def test_t1_residual_equals_surface_diff_minus_blended():
    df = _synthetic_frame(50, seed=2)
    df["surface"] = "Hard"
    added = gm.t1_added_raw(df)
    blended = (df["p1_hold_pct_asof"] - df["p2_hold_pct_asof"]).to_numpy()
    surf_diff = (df["p1_hold_pct_hard_asof"] - df["p2_hold_pct_hard_asof"]).to_numpy()
    np.testing.assert_allclose(added[:, 0], blended)
    np.testing.assert_allclose(added[:, 1], surf_diff - blended)


def test_t2_low_regime_requires_both_players_below_median():
    df = _synthetic_frame(100, seed=3)
    df["surface"] = "Clay"
    med = gm.train_surface_median(df)
    added = gm.t2_added_raw(df, med)
    surf_diff = (df["p1_hold_pct_clay_asof"] - df["p2_hold_pct_clay_asof"]).to_numpy()
    low_regime = ((df["p1_hold_pct_clay_asof"] < med) & (df["p2_hold_pct_clay_asof"] < med)).to_numpy()
    np.testing.assert_allclose(added[:, 0], surf_diff)
    np.testing.assert_allclose(added[:, 1], surf_diff * low_regime)


def test_train_surface_median_is_train_only_not_pooled_with_test():
    train = _synthetic_frame(100, seed=4)
    test = _synthetic_frame(100, seed=5)
    test["p1_hold_pct_hard_asof"] += 10.0  # test-only outlier must NOT move the median
    med_train = gm.train_surface_median(train)
    combined = pd.concat([train, test], ignore_index=True)
    med_combined = gm.train_surface_median(combined)
    assert med_train != pytest.approx(med_combined)


def test_coverage_mask_respects_min_prior():
    df = _synthetic_frame(30, seed=6)
    df["surface"] = "Hard"
    df.loc[0, "p1_n_prior"] = 2  # below MIN_PRIOR=5
    surf_diff = gm._surface_hold_diff(df)
    cov = gm._coverage_mask(df, surf_diff)
    assert not cov[0]
    assert cov[1:].all()


def test_score_candidate_falls_back_on_missing_surface_coverage():
    """A row with NaN surface-hold ingredients scores IDENTICAL to p_base (fallback)."""
    df = _synthetic_frame(300, seed=7, surface_coverage=0.5)
    df["surface"] = "Hard"
    added_tr, added_te = gm.added_raw_for("tennis_surface_hold_regime", df, df)
    base_fit = gm.fit_base(df)
    valid = np.all(np.isfinite(added_tr), axis=1)
    cand_fit, added_std = gm.fit_candidate(df[valid.tolist()], added_tr[valid])
    p_base = gm.score_base(df, base_fit)
    p_cand = gm.score_candidate(df, cand_fit, added_std, added_te, p_base)
    missing_mask = ~valid
    assert missing_mask.sum() > 0
    assert np.array_equal(p_cand[missing_mask], p_base[missing_mask])


def test_fit_and_score_corpus_produces_stackrows_matching_test_split():
    df = _synthetic_frame(400, seed=8)
    rows = g.fit_and_score_corpus(df, "tennis_surface_hold_regime")
    expected_test_n = len(sf.expanding_window_splits(len(df), 0.5, 1)[0].test_idx)
    assert len(rows) == expected_test_n
    for r in rows:
        assert 0.0 <= r.p_base <= 1.0
        assert 0.0 <= r.p_candidate <= 1.0
        assert r.y in (0.0, 1.0)


def test_fit_and_score_corpus_t2_candidate_runs():
    df = _synthetic_frame(400, seed=9)
    rows = g.fit_and_score_corpus(df, "tennis_surface_serve_return_gap")
    assert len(rows) > 0


def test_close_brier_for_frame_covered_subset_only():
    df = _synthetic_frame(100, seed=10)
    df.loc[:20, "p_close"] = np.nan
    brier, cov = gm.close_brier_for_frame(df)
    assert cov == 79
    assert 0.0 <= brier <= 1.0


def test_close_brier_for_frame_zero_coverage_returns_nan():
    df = _synthetic_frame(20, seed=11)
    df["p_close"] = np.nan
    brier, cov = gm.close_brier_for_frame(df)
    assert cov == 0
    assert np.isnan(brier)


def test_plant_null_permutes_surface_cols_and_scores_a_boolean():
    df = _synthetic_frame(300, seed=12)
    rng = np.random.default_rng(0)
    result = g._plant_null(df, "tennis_surface_hold_regime", rng)
    assert isinstance(result, bool)


def test_seed_stability_p10_runs_five_refits():
    df = _synthetic_frame(300, seed=13)
    p10 = g._seed_stability_p10(df, "tennis_surface_hold_regime")
    assert np.isfinite(p10)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
