"""tests.platform.test_soccer_interaction_gate -- unit tests for A1-S
(soccer_interaction_s1/s2). Synthetic canned frames per test_soccer_home_sot_
replication.py's own convention -- fast, no real-parquet fit for the unit
tests; the module's own __main__ smoke run (not this file) is the real-data
check. ASCII; per-file only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.soccer import interaction_gate as ig
from domains.soccer import interaction_gate_math as gm
from domains.soccer import interaction_gate_select as gs
from scripts.platformkit.combo import stack_fit as sf
from scripts.platformkit.combo.stack_gate_pregame import StackRow


def _synthetic_frame(n: int, seed: int, missing_frac: float = 0.0) -> pd.DataFrame:
    """A canned frame with the SAME columns build_league_frame's covered output
    has for BOTH candidates' raw ingredients."""
    rng = np.random.default_rng(seed)
    p_over25 = np.clip(rng.normal(0.5, 0.1, size=n), 0.05, 0.95)
    home_sot = rng.normal(5.0, 1.5, size=n)
    away_sot = rng.normal(4.5, 1.5, size=n)
    home_xg = rng.normal(1.4, 0.4, size=n)
    away_xg = rng.normal(1.2, 0.4, size=n)
    diff_xg_sup = (home_xg - away_xg) + rng.normal(0, 0.2, size=n)
    if missing_frac > 0:
        mask = rng.uniform(0, 1, size=n) < missing_frac
        home_sot = np.where(mask, np.nan, home_sot)
    y = (rng.uniform(0, 1, size=n) < p_over25).astype(float)
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "target_over25": y,
        "date": pd.date_range("2018-01-01", periods=n, freq="D"),
        "p_over25": p_over25,
        "home_sot_for_l10": home_sot, "away_sot_for_l10": away_sot,
        "home_xg_for_asof": home_xg, "away_xg_for_asof": away_xg,
        "diff_xg_supremacy_asof": diff_xg_sup,
        "home_n_prior": 20, "away_n_prior": 20,
    })


# --------------------------------------------------------------------------- #
# interaction_gate_math
# --------------------------------------------------------------------------- #

def test_s1_raw_ingredients_sums_both_teams():
    df = _synthetic_frame(50, seed=1)
    tot_sot, tot_xg = gm.s1_raw_ingredients(df)
    np.testing.assert_allclose(tot_sot, (df["home_sot_for_l10"] + df["away_sot_for_l10"]).to_numpy())
    np.testing.assert_allclose(tot_xg, (df["home_xg_for_asof"] + df["away_xg_for_asof"]).to_numpy())


def test_s1_raw_ingredients_nan_propagates_when_either_half_missing():
    df = _synthetic_frame(10, seed=2)
    df.loc[0, "home_sot_for_l10"] = np.nan
    tot_sot, _ = gm.s1_raw_ingredients(df)
    assert np.isnan(tot_sot[0])


def test_s2_raw_ingredients_net_sot_and_diff_xg():
    df = _synthetic_frame(50, seed=3)
    net_sot, diff_xg = gm.s2_raw_ingredients(df)
    np.testing.assert_allclose(net_sot, (df["home_sot_for_l10"] - df["away_sot_for_l10"]).to_numpy())
    np.testing.assert_allclose(diff_xg, df["diff_xg_supremacy_asof"].to_numpy())


def test_s1_fit_returns_3feature_fit_and_train_only_median():
    df = _synthetic_frame(400, seed=4)
    fit, std, median_xg = gm.s1_fit(df)
    assert fit.weights.shape == (4,)  # intercept + base_logit + sot_z + sot_z*regime
    assert std.means.shape == (1,)
    tot_sot, tot_xg = gm.s1_raw_ingredients(df)
    assert np.isclose(median_xg, np.nanmedian(tot_xg))


def test_s2_fit_returns_3feature_fit():
    df = _synthetic_frame(400, seed=5)
    fit, std = gm.s2_fit(df)
    assert fit.weights.shape == (4,)  # intercept + base_logit + abs_diff_xg_z + product
    assert std.means.shape == (1,)


def test_s1_score_falls_back_on_missing_ingredient():
    df = _synthetic_frame(300, seed=6, missing_frac=0.5)
    base_fit = gm.fit_base(df)
    p_base = gm.score_base(df, base_fit)
    fit, std, median_xg = gm.s1_fit(df)
    p_cand = gm.s1_score(df, fit, std, median_xg, p_base)
    tot_sot, _ = gm.s1_raw_ingredients(df)
    missing_mask = np.isnan(tot_sot)
    assert missing_mask.any()
    assert np.array_equal(p_cand[missing_mask], p_base[missing_mask])


def test_s2_score_falls_back_on_missing_ingredient():
    df = _synthetic_frame(300, seed=7, missing_frac=0.5)
    base_fit = gm.fit_base(df)
    p_base = gm.score_base(df, base_fit)
    fit, std = gm.s2_fit(df)
    p_cand = gm.s2_score(df, fit, std, p_base)
    net_sot, _ = gm.s2_raw_ingredients(df)
    missing_mask = np.isnan(net_sot)
    assert missing_mask.any()
    assert np.array_equal(p_cand[missing_mask], p_base[missing_mask])


def test_covered_filters_on_min_prior_and_added_cols():
    df = _synthetic_frame(50, seed=8)
    df.loc[0, "home_n_prior"] = 0            # below MIN_PRIOR -> excluded
    df.loc[1, "home_sot_for_l10"] = np.nan   # missing ingredient -> excluded
    out = gm._covered(df, ("home_sot_for_l10", "home_xg_for_asof"))
    assert len(out) == 48
    assert "e0" not in out["event_id"].to_list()
    assert "e1" not in out["event_id"].to_list()


# --------------------------------------------------------------------------- #
# interaction_gate_select / interaction_gate orchestration
# --------------------------------------------------------------------------- #

def test_fit_and_score_league_s1_and_s2_produce_stackrows_matching_test_split():
    df = _synthetic_frame(400, seed=9)
    for cand in ("S1", "S2"):
        rows = gs.fit_and_score_league(df, cand)
        expected_n = len(sf.expanding_window_splits(len(df), 0.5, 1)[0].test_idx)
        assert len(rows) == expected_n
        for r in rows:
            assert 0.0 <= r.p_base <= 1.0
            assert 0.0 <= r.p_candidate <= 1.0
            assert r.y in (0.0, 1.0)
            assert len(r.added_raw) == 2


def test_select_fn_between_s1_s2_returns_one_of_the_two_names():
    frames = {"S1": {"A": _synthetic_frame(300, seed=10)},
             "S2": {"A": _synthetic_frame(300, seed=10)}}
    select = gs.select_fn_between_s1_s2(frames)
    game_ids = [f"e{i}" for i in range(150)]  # inner half, arbitrary subset
    picked = select(game_ids)
    assert picked in ("S1", "S2")


def test_plant_null_permutes_sot_columns_and_returns_bool():
    df = _synthetic_frame(300, seed=11)
    plant = gs.plant_null_fn({"A": df}, "S1")
    rng = np.random.default_rng(42)
    result = plant(rng)
    assert isinstance(result, bool)


def test_seed_stability_p10_returns_finite_float():
    df = _synthetic_frame(400, seed=12)
    p10 = gs.seed_stability_p10(df, "S2")
    assert np.isfinite(p10)


def test_per_league_replication_floor_needs_4_of_6():
    """3 leagues passing (candidate shrunk toward the true label = genuinely
    better calibrated) must NOT meet the floor of 4 -- same contract as the
    home_sot_replication_gate precedent."""
    def _mk_rows(n: int, beats_base: bool, seed: int):
        rng = np.random.default_rng(seed)
        y = rng.integers(0, 2, size=n).astype(float)
        p_base = np.clip(rng.normal(0.5, 0.05, size=n), 0.05, 0.95)
        if beats_base:
            p_cand = np.clip(0.3 * p_base + 0.7 * y * 0.9 + 0.7 * (1 - y) * 0.1, 0.02, 0.98)
        else:
            p_cand = p_base
        return [StackRow(event_id=f"g{i}", y=float(y[i]), p_base=float(p_base[i]),
                         p_candidate=float(p_cand[i]), added_raw=(0.0, 0.0))
                for i in range(n)]

    league_rows = {
        "A": _mk_rows(500, True, 1), "B": _mk_rows(500, True, 2),
        "C": _mk_rows(500, True, 3), "D": _mk_rows(500, False, 4),
        "E": _mk_rows(500, False, 5), "F": _mk_rows(500, False, 6),
    }
    result = ig.per_league_replication(league_rows, eps=0.05)
    assert result["n_pass"] == 3
    assert result["floor_met"] is False  # 3 < 4


def test_close_brier_for_leagues_returns_nan_pair_when_no_join_matches(tmp_path, monkeypatch):
    """No event_id overlaps _ODDS -> both briers are nan (honest 'no data'
    signal, never a fabricated 0.0)."""
    empty_odds = pd.DataFrame({"event_id": ["zzz-no-match"],
                               "ou_close_over": [2.0], "ou_close_under": [1.9]})
    odds_path = tmp_path / "odds.parquet"
    empty_odds.to_parquet(odds_path)
    monkeypatch.setattr(gm, "_ODDS", odds_path)
    rows = {"A": gs.fit_and_score_league(_synthetic_frame(200, seed=13), "S1")}
    stack_brier, close_brier = ig.close_brier_for_leagues(rows)
    assert np.isnan(stack_brier) and np.isnan(close_brier)


def test_close_brier_for_leagues_devigs_decimal_odds_not_raw():
    """The close probability must come from devigging ou_close_over/_under
    (decimal odds), NOT a raw column misread as a probability -- a close near
    an implausible extreme would signal the devig regressed to reading odds
    directly (same landmine test as home_sot_replication_gate)."""
    odds = pd.DataFrame({"event_id": ["e0", "e1"],
                         "ou_close_over": [2.00, 1.90], "ou_close_under": [1.80, 1.95]})
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "odds.parquet"
        odds.to_parquet(p)
        rows = {"A": [StackRow(event_id="e0", y=1.0, p_base=0.5, p_candidate=0.5,
                               added_raw=(0.0, 0.0)),
                     StackRow(event_id="e1", y=0.0, p_base=0.5, p_candidate=0.5,
                             added_raw=(0.0, 0.0))]}
        orig = gm._ODDS
        gm._ODDS = p
        try:
            _, close_brier = ig.close_brier_for_leagues(rows)
        finally:
            gm._ODDS = orig
    assert 0.0 <= close_brier <= 1.0
    assert close_brier < 0.5  # devigged O/U 2.5 closes cluster near 0.5 implied prob


def test_k_cum_is_15_and_eps_eff_tighter_than_v1_family3():
    """A1 states K_cum=15 (13 carried + 2 new) -> eps_eff=0.05/15=0.003333,
    strictly tighter than the solo family's 0.05/13=0.003846 -- the budget
    continues, never resets."""
    from scripts.platformkit.combo.fwer_budget import eps_eff
    assert ig.K_CUM == 15
    eps_a1s = eps_eff(0.05, ig.K_CUM)
    eps_family3 = eps_eff(0.05, 13)
    assert eps_a1s < eps_family3
    assert abs(eps_a1s - 0.003333) < 1e-5


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
