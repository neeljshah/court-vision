"""scripts.platformkit.combo.test_run_nba_teamadv_stack_v1 -- corpus-assembly
unit tests (synthetic). The real gate run is a __main__ guard (run.py, already
run+verified live against the real parquet corpora during the lane); this file
only exercises the pure fit/score/fallback functions on canned frames so it
never touches the real corpus. ASCII; per-file only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.combo import run_nba_teamadv_stack_v1 as m
from scripts.platformkit.combo import stack_fit as sf


def _synthetic_frame(n: int, seed: int, added_coverage: float = 1.0) -> pd.DataFrame:
    """A canned frame with the SAME columns build_corpus_frame produces."""
    rng = np.random.default_rng(seed)
    p_home_elo = np.clip(rng.normal(0.5, 0.1, size=n), 0.05, 0.95)
    cols = {c: rng.normal(0.0, 1.0, size=n) for c in m.TA1_COLS + m.TA2_COLS}
    if added_coverage < 1.0:
        mask = rng.uniform(0, 1, size=n) > added_coverage
        for c in cols:
            cols[c] = np.where(mask, np.nan, cols[c])
    y = (rng.uniform(0, 1, size=n) < p_home_elo).astype(float)
    df = pd.DataFrame({
        "game_id": [f"g{i}" for i in range(n)],
        "home_win": y,
        "date": pd.date_range("2022-10-01", periods=n, freq="D"),
        "season": ["2022-23"] * n,
        "p_home_elo": p_home_elo,
    })
    for c, v in cols.items():
        df[c] = v
    return df


def test_fit_base_is_one_feature_logistic():
    """A3 base spec: [1, logit(p_elo)] ONLY -- SAME form as V1/A2 Family 2."""
    df = _synthetic_frame(500, seed=1)
    fit = m._fit_base(df)
    assert fit.weights.shape == (2,)  # intercept + elo_logit ONLY


def test_fit_candidate_ta1_shape():
    df = _synthetic_frame(500, seed=2)
    fit, added_std = m._fit_candidate(df, list(m.TA1_COLS))
    assert fit.weights.shape == (4,)  # intercept + elo_logit + 2 added (off/def rtg)
    assert added_std.means.shape == (2,)


def test_fit_candidate_ta2_shape():
    df = _synthetic_frame(500, seed=3)
    fit, added_std = m._fit_candidate(df, list(m.TA2_COLS))
    assert fit.weights.shape == (5,)  # intercept + elo_logit + 3 added (four-factors)
    assert added_std.means.shape == (3,)


def test_score_base_returns_valid_probabilities():
    df = _synthetic_frame(300, seed=4)
    fit = m._fit_base(df)
    p = m._score_base(df, fit)
    assert p.shape == (300,)
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_score_candidate_falls_back_on_missing_added_feature():
    """A row with NaN off_rtg_diff_asof scores IDENTICAL to p_base (fallback contract)."""
    df = _synthetic_frame(200, seed=5, added_coverage=0.5)
    base_fit = m._fit_base(df)
    cand_fit, added_std = m._fit_candidate(df, ["off_rtg_diff_asof"])
    p_base = m._score_base(df, base_fit)
    p_cand = m._score_candidate(df, cand_fit, added_std, ["off_rtg_diff_asof"], p_base)
    missing_mask = df["off_rtg_diff_asof"].isna().to_numpy()
    assert np.array_equal(p_cand[missing_mask], p_base[missing_mask])


def test_fit_and_score_corpus_produces_stackrows_matching_test_split():
    df = _synthetic_frame(400, seed=6)
    rows = m.fit_and_score_corpus(df, list(m.TA1_COLS))
    expected_test_n = len(sf.expanding_window_splits(len(df), 0.5, 1)[0].test_idx)
    assert len(rows) == expected_test_n
    for r in rows:
        assert 0.0 <= r.p_base <= 1.0
        assert 0.0 <= r.p_candidate <= 1.0
        assert r.y in (0.0, 1.0)
        assert len(r.added_raw) == 2


def test_fit_and_score_corpus_full_missing_coverage_all_fallback():
    df = _synthetic_frame(300, seed=7, added_coverage=0.0)
    rows = m.fit_and_score_corpus(df, list(m.TA2_COLS))
    for r in rows:
        assert r.p_base == r.p_candidate  # every row fell back to base


def test_fallback_count_matches_injected_missing_rows():
    """fallback_count reports the SAME row set score_with_fallback would use base
    for -- i.e. rows missing >=1 added col (either side n_prior=0, A3 corpus rule)."""
    df = _synthetic_frame(200, seed=8, added_coverage=0.6)
    n_fb = m.fallback_count(df, list(m.TA1_COLS))
    has_all = np.isfinite(df["off_rtg_diff_asof"].to_numpy(float)) & \
              np.isfinite(df["def_rtg_diff_asof"].to_numpy(float))
    assert n_fb == int((~has_all).sum())
    assert n_fb > 0  # coverage < 1.0 guarantees >=1 fallback row


def test_fallback_count_zero_when_full_coverage():
    df = _synthetic_frame(150, seed=9, added_coverage=1.0)
    assert m.fallback_count(df, list(m.TA2_COLS)) == 0


def test_close_overlap_and_brier_zero_when_no_ids_match():
    base = pd.DataFrame({"game_id": ["z1", "z2"]})
    n_overlap, br = m.close_overlap_and_brier(base, {})
    # Real close corpus on disk almost certainly shares 0 ids with these fake ids.
    assert n_overlap == 0
    assert br is None


def test_null_floor_prescreen_returns_none_when_no_floor_cached():
    """A3 clause 4: prescreen is optional -- an uncached (sport, unit) combo must
    proceed to the full ceremony (None), never raise or silently REJECT."""
    result = m._null_floor_prescreen("nba", "__no_such_unit_ever__", 2, 0.001)
    assert result is None


def test_k_cum_pinned_to_six():
    """A3 clause 2: K_prior=4 (V1 Family2 P1/P2 + A2 N1/N2) + K_new=2 (TA1/TA2)."""
    assert m.K_CUM == 6


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
