"""tests.platform.test_soccer_home_sot_replication -- unit tests for Family 3
(soccer_home_sot_replication_v1). Synthetic canned frames per test_mlb_pregame_
stack_gate.py's own convention -- fast, no real-parquet dependency for the fit/
score unit tests; a SEPARATE small block exercises wc_corpus_check against the
real on-disk build_states('soccer_intl') (cheap, no parquet fit involved).
ASCII; per-file only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.soccer import home_sot_replication_gate as m
from scripts.platformkit.combo import stack_fit as sf


def _synthetic_league_frame(n: int, seed: int, added_coverage: float = 1.0) -> pd.DataFrame:
    """A canned frame with the SAME columns build_league_frame's covered output has."""
    rng = np.random.default_rng(seed)
    p_over25 = np.clip(rng.normal(0.5, 0.1, size=n), 0.05, 0.95)
    sot_l10 = rng.normal(4.0, 1.5, size=n)
    if added_coverage < 1.0:
        mask = rng.uniform(0, 1, size=n) > added_coverage
        sot_l10 = np.where(mask, np.nan, sot_l10)
    y = (rng.uniform(0, 1, size=n) < p_over25).astype(float)
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "target_over25": y,
        "date": pd.date_range("2018-01-01", periods=n, freq="D"),
        "p_over25": p_over25,
        "home_sot_for_l10": sot_l10,
        "home_n_prior": 20, "away_n_prior": 20,
    })


def test_fit_base_returns_1feature_fit():
    df = _synthetic_league_frame(400, seed=1)
    fit, std = m._fit_base(df)
    assert fit.weights.shape == (2,)  # intercept + p_over25_logit
    assert std is None


def test_fit_candidate_returns_2feature_fit_and_standardizer():
    df = _synthetic_league_frame(400, seed=2)
    fit, std = m._fit_candidate(df)
    assert fit.weights.shape == (3,)  # intercept + base_logit + sot_z
    assert std.means.shape == (1,)


def test_score_candidate_falls_back_on_missing_feature():
    """A row with NaN home_sot_for_l10 scores IDENTICAL to p_base (fallback contract)."""
    df = _synthetic_league_frame(300, seed=3, added_coverage=0.5)
    base_fit, _ = m._fit_base(df)
    cand_fit, cand_std = m._fit_candidate(df)
    p_base = m._score_base(df, base_fit)
    p_cand = m._score_candidate(df, cand_fit, cand_std, p_base)
    missing_mask = df["home_sot_for_l10"].isna().to_numpy()
    assert np.array_equal(p_cand[missing_mask], p_base[missing_mask])


def test_covered_filters_on_min_prior_and_feature_presence():
    df = _synthetic_league_frame(50, seed=4)
    df.loc[0, "home_n_prior"] = 0     # below MIN_PRIOR -> excluded
    df.loc[1, "home_sot_for_l10"] = np.nan  # missing feature -> excluded
    out = m._covered(df)
    assert len(out) == 48
    assert "e0" not in out["event_id"].to_list()
    assert "e1" not in out["event_id"].to_list()


def test_fit_and_score_league_produces_stackrows_matching_test_split():
    df = _synthetic_league_frame(400, seed=5)
    rows = m.fit_and_score_league(df)
    expected_n = len(sf.expanding_window_splits(len(df), 0.5, 1)[0].test_idx)
    assert len(rows) == expected_n
    for r in rows:
        assert 0.0 <= r.p_base <= 1.0
        assert 0.0 <= r.p_candidate <= 1.0
        assert r.y in (0.0, 1.0)


def test_per_league_replication_floor_needs_4_of_6():
    """3 leagues passing (candidate shrunk toward the true label = genuinely
    better calibrated) must NOT meet the floor of 4."""
    def _mk_rows(n: int, beats_base: bool, seed: int):
        rng = np.random.default_rng(seed)
        y = rng.integers(0, 2, size=n).astype(float)
        p_base = np.clip(rng.normal(0.5, 0.05, size=n), 0.05, 0.95)
        if beats_base:
            p_cand = np.clip(0.3 * p_base + 0.7 * y * 0.9 + 0.7 * (1 - y) * 0.1, 0.02, 0.98)
        else:
            p_cand = p_base
        return [m.StackRow(event_id=f"g{i}", y=float(y[i]), p_base=float(p_base[i]),
                           p_candidate=float(p_cand[i]), added_raw=(0.0,))
                for i in range(n)]

    league_rows = {
        "A": _mk_rows(500, True, 1), "B": _mk_rows(500, True, 2),
        "C": _mk_rows(500, True, 3), "D": _mk_rows(500, False, 4),
        "E": _mk_rows(500, False, 5), "F": _mk_rows(500, False, 6),
    }
    result = m.per_league_replication(league_rows, eps=0.05)
    assert result["n_pass"] == 3
    assert result["floor_met"] is False  # 3 < 4


def test_close_brier_for_leagues_returns_nan_pair_when_no_join_matches(tmp_path, monkeypatch):
    """No event_id overlaps _ODDS -> both briers are nan (honest 'no data' signal,
    never a fabricated 0.0)."""
    empty_odds = pd.DataFrame({"event_id": ["zzz-no-match"],
                               "ou_close_over": [2.0], "ou_close_under": [1.9]})
    odds_path = tmp_path / "odds.parquet"
    empty_odds.to_parquet(odds_path)
    monkeypatch.setattr(m, "_ODDS", odds_path)
    rows = {"A": m.fit_and_score_league(_synthetic_league_frame(200, seed=7))}
    stack_brier, close_brier = m.close_brier_for_leagues(rows)
    assert np.isnan(stack_brier) and np.isnan(close_brier)


def test_close_brier_for_leagues_devigs_decimal_odds_not_raw():
    """The close probability must come from devigging ou_close_over/_under
    (decimal odds), NOT a raw column misread as a probability -- a close near
    an implausible extreme (e.g. > about 0.9 or < about 0.1 on a roughly 50/50
    O/U 2.5 market) would signal the devig regressed to reading odds directly."""
    odds = pd.DataFrame({"event_id": ["e0", "e1"],
                         "ou_close_over": [2.00, 1.90], "ou_close_under": [1.80, 1.95]})
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "odds.parquet"
        odds.to_parquet(p)
        rows = {"A": [m.StackRow(event_id="e0", y=1.0, p_base=0.5, p_candidate=0.5,
                                 added_raw=(0.0,)),
                     m.StackRow(event_id="e1", y=0.0, p_base=0.5, p_candidate=0.5,
                               added_raw=(0.0,))]}
        orig = m._ODDS
        m._ODDS = p
        try:
            _, close_brier = m.close_brier_for_leagues(rows)
        finally:
            m._ODDS = orig
    assert 0.0 <= close_brier <= 1.0
    assert close_brier < 0.5  # devigged O/U 2.5 closes cluster near 0.5 implied prob


def test_wc_corpus_check_against_real_build_states_confirms_column_absent():
    """Q2 verification against the REAL on-disk backfill: home_sot_for_l10 must
    be absent from build_states('soccer_intl') -- candidate 2 stays dropped."""
    result = m.wc_corpus_check()
    assert result["has_home_sot_for_l10"] is False
    assert result["candidate_2_dropped"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
