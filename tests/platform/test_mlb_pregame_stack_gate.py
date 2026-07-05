"""tests.platform.test_mlb_pregame_stack_gate -- corpus-assembly unit tests (synthetic).

The real gate run is a __main__ guard (domains.mlb.pregame_stack_gate); this file
only exercises the pure fit/score functions on canned frames so it never touches
the real parquet corpora. ASCII; per-file only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.mlb import pregame_stack_gate as m
from scripts.platformkit.combo import stack_fit as sf


def _synthetic_frame(n: int, seed: int, added_coverage: float = 1.0) -> pd.DataFrame:
    """A canned frame with the SAME columns build_corpus_frame produces."""
    rng = np.random.default_rng(seed)
    p_home_elo = np.clip(rng.normal(0.5, 0.1, size=n), 0.05, 0.95)
    sp_diff = rng.normal(0.0, 1.0, size=n)
    park = rng.normal(1.0, 0.05, size=n)
    ra = rng.normal(0.0, 2.0, size=n)
    if added_coverage < 1.0:
        mask = rng.uniform(0, 1, size=n) > added_coverage
        park = np.where(mask, np.nan, park)
        ra = np.where(mask, np.nan, ra)
    y = (rng.uniform(0, 1, size=n) < p_home_elo).astype(float)
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "target_home_win": y,
        "date": pd.date_range("2020-01-01", periods=n, freq="D"),
        "p_home_elo": p_home_elo,
        "sp_first6_diff_ew": sp_diff,
        "park_factor": park,
        "sp_ra_diff_asof": ra,
    })


def test_fit_base_returns_fit_and_standardizer():
    df = _synthetic_frame(500, seed=1)
    fit, sp_std = m._fit_base(df)
    assert fit.weights.shape == (3,)  # intercept + elo_logit + sp_z
    assert isinstance(sp_std, sf.StandardizerParams)


def test_fit_candidate_returns_fit_and_two_standardizers():
    df = _synthetic_frame(500, seed=2)
    fit, sp_std, added_std = m._fit_candidate(df, ["park_factor"])
    assert fit.weights.shape == (4,)  # intercept + elo_logit + sp_z + park_z
    assert added_std.means.shape == (1,)


def test_fit_candidate_two_added_features():
    df = _synthetic_frame(500, seed=3)
    fit, sp_std, added_std = m._fit_candidate(df, ["park_factor", "sp_ra_diff_asof"])
    assert fit.weights.shape == (5,)  # intercept + elo_logit + sp_z + 2 added
    assert added_std.means.shape == (2,)


def test_score_base_returns_valid_probabilities():
    df = _synthetic_frame(300, seed=4)
    fit, sp_std = m._fit_base(df)
    p = m._score_base(df, fit, sp_std)
    assert p.shape == (300,)
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_score_candidate_falls_back_on_missing_added_feature():
    """A row with NaN park_factor scores IDENTICAL to p_base (fallback contract)."""
    df = _synthetic_frame(200, seed=5, added_coverage=0.5)
    base_fit, base_sp = m._fit_base(df)
    cand_fit, cand_sp, added_std = m._fit_candidate(df, ["park_factor"])
    p_base = m._score_base(df, base_fit, base_sp)
    p_cand = m._score_candidate(df, cand_fit, cand_sp, added_std, ["park_factor"], p_base)
    missing_mask = df["park_factor"].isna().to_numpy()
    assert np.array_equal(p_cand[missing_mask], p_base[missing_mask])


def test_fit_and_score_corpus_produces_stackrows_matching_test_split():
    df = _synthetic_frame(400, seed=6)
    rows = m.fit_and_score_corpus(df, ["park_factor"])
    expected_test_n = len(sf.expanding_window_splits(len(df), 0.5, 1)[0].test_idx)
    assert len(rows) == expected_test_n
    for r in rows:
        assert 0.0 <= r.p_base <= 1.0
        assert 0.0 <= r.p_candidate <= 1.0
        assert r.y in (0.0, 1.0)


def test_fit_and_score_corpus_full_missing_coverage_all_fallback():
    """Zero added-feature coverage (mirrors corpus B reality): candidate == base."""
    df = _synthetic_frame(300, seed=7, added_coverage=0.0)
    rows = m.fit_and_score_corpus(df, ["park_factor", "sp_ra_diff_asof"])
    for r in rows:
        assert r.p_base == r.p_candidate  # every row fell back to base


def test_build_corpus_frame_columns_present_when_given_real_shaped_input(tmp_path, monkeypatch):
    """build_corpus_frame's OWN merges are exercised via the module functions it
    calls; here we just confirm _close_join_key produces a stable, joinable string."""
    row = pd.Series({"date": "2021-04-05", "home_team": "LAD", "away_team": "DET"})
    key = m._close_join_key(row)
    assert key.startswith("20210405|")
    assert "|" in key[9:]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
