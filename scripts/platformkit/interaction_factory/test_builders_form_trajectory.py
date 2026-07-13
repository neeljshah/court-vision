"""Per-file test for interaction_factory.builders_form_trajectory (Sonnet
build lane, 149870ff follow-on).
Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_form_trajectory.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.interaction_factory import builders_form_trajectory as bft
from scripts.platformkit.interaction_factory import generator as GEN


# --------------------------------------------------------------------------
# 1. Template registration shape.
def test_self_cross_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["nba_form_self_cross"]
    assert tpl["sport"] == "basketball_nba"
    assert tpl["atomic_unit"] == "player_game"
    assert tpl["outcome"] == "efg"
    assert tpl["pairing"] == "self_cross"
    assert tpl["left_pool"] == {"static_pool": "nba_form_asof"}
    assert tpl["feature_builder"] == "nba_form_self_cross_asof"


def test_state_conditioner_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["nba_form_state_conditioner"]
    assert tpl["sport"] == "basketball_nba"
    assert tpl["atomic_unit"] == "player_game"
    assert tpl["outcome"] == "efg"
    assert tpl["pairing"] == "cross"
    assert tpl["left_pool"] == {"static_pool": "nba_form_asof"}
    assert tpl["right_pool"] == {"attributes": ["late_clock_efg", "clutch_efg"]}
    assert tpl["feature_builder"] == "nba_form_state_conditioner_asof"


def test_static_pool_has_8_cols_excluding_n_prior_games_and_baseline_pts():
    pool = GEN.STATIC_POOLS["nba_form_asof"]
    assert len(pool) == 8
    assert "n_prior_games" not in pool
    assert "baseline_pts" not in pool


def test_builders_registered_in_runner():
    from scripts.platformkit.interaction_factory import runner as RUN
    assert RUN._BUILDERS["nba_form_self_cross_asof"] is bft._nba_form_self_cross_builder
    assert RUN._BUILDERS["nba_form_state_conditioner_asof"] is bft._nba_form_state_conditioner_builder


# --------------------------------------------------------------------------
# 2. Candidate enumeration non-empty (C(8,2)=28 self-cross, 8*2=16 conditioner).
def test_self_cross_enumeration_nonempty():
    cands = GEN.enumerate_candidates("nba_form_self_cross")
    assert len(cands) == 28
    assert all(isinstance(c, GEN.Candidate) for c in cands)
    assert all(c.feature_builder == "nba_form_self_cross_asof" for c in cands)


def test_state_conditioner_enumeration_nonempty():
    cands = GEN.enumerate_candidates("nba_form_state_conditioner")
    assert len(cands) == 16
    pairs = {(c.attr_a, c.attr_b) for c in cands}
    assert ("l5_pts", "late_clock_efg") in pairs
    assert ("dev_pts_vs_baseline", "clutch_efg") in pairs


# --------------------------------------------------------------------------
# 3. Builder frames: synthetic form_trajectory_asof + player_offense_events.
def _form(n=4):
    return pd.DataFrame({
        "player_id": [1, 1, 2, 2],
        "season": ["2024-25"] * 4,
        "game_id": ["g0", "g1", "g0", "g1"],
        "n_prior_games": [0, 5, 0, 5],
        "l5_pts": [float("nan"), 20.0, float("nan"), 10.0],
        "l10_pts": [float("nan"), 18.0, float("nan"), 9.0],
        "l5_min": [float("nan"), 30.0, float("nan"), 25.0],
        "l10_min": [float("nan"), 29.0, float("nan"), 24.0],
        "l5_ts_pct": [float("nan"), 0.55, float("nan"), 0.50],
        "l10_ts_pct": [float("nan"), 0.54, float("nan"), 0.49],
        "trend_pts_slope10": [float("nan"), 1.5, float("nan"), -0.5],
        "baseline_pts": [float("nan"), 19.0, float("nan"), 9.5],
        "dev_pts_vs_baseline": [float("nan"), 1.0, float("nan"), 0.5],
    })


def _poe(n=4):
    return pd.DataFrame({
        "player_id": [1, 1, 2, 2],
        "game_id": ["g0", "g1", "g0", "g1"],
        "date": pd.to_datetime(["2024-11-01", "2024-11-03", "2024-11-01", "2024-11-03"]),
        "total_fgm": [8, 10, 4, 5],
        "total_fga": [16, 18, 10, 12],
        "above_break_3_fgm": [2, 3, 1, 1],
        "corner3_fgm": [0, 0, 0, 0],
        "late_clock_fgm": [1, 2, 1, 1], "late_clock_fga": [2, 3, 2, 3], "late_clock_fg3m": [0, 1, 0, 0],
        "clutch_fgm": [1, 1, 0, 1], "clutch_fga": [2, 2, 1, 2], "clutch_fg3m": [0, 0, 0, 0],
    })


def test_self_cross_frame_sets_y_and_asof_cols():
    out = bft.build_nba_form_self_cross_frame(_form(), _poe(), ["l5_pts", "l10_pts"])
    assert {"asof__l5_pts", "asof__l10_pts", "y"} <= set(out.columns)
    assert len(out) == 4
    # g1 row for player 1: y = (10 + 0.5*3)/18
    row = out[(out["player_id"] == 1) & (out["game_id"] == "g1")].iloc[0]
    assert abs(row["y"] - (10 + 0.5 * 3) / 18) < 1e-9
    assert row["asof__l5_pts"] == 20.0


def test_self_cross_sanity_trap_n_prior_games_zero_rows_stay_nan():
    """n_prior_games==0 rows (first game of a player/season) must carry NaN
    features straight through -- never fabricated by this builder."""
    out = bft.build_nba_form_self_cross_frame(_form(), _poe(), ["l5_pts", "dev_pts_vs_baseline"])
    g0_rows = out[out["game_id"] == "g0"]
    assert len(g0_rows) == 2
    assert g0_rows["asof__l5_pts"].isna().all()
    assert g0_rows["asof__dev_pts_vs_baseline"].isna().all()


def test_state_conditioner_frame_has_form_and_state_cols():
    out = bft.build_nba_form_state_conditioner_frame(
        _form(), _poe(), ["l5_pts", "clutch_efg"], min_prior_att=1)
    assert {"asof__l5_pts", "asof__clutch_efg", "y"} <= set(out.columns)
    # player 1's g1 clutch_efg is strictly-prior (from g0: 1fgm/2fga, no 3s) = 0.5
    row = out[(out["player_id"] == 1) & (out["game_id"] == "g1")].iloc[0]
    assert abs(row["asof__clutch_efg"] - 0.5) < 1e-9
    # g0 (no prior games) -> NaN clutch_efg too (min_prior_att gate)
    g0_rows = out[out["game_id"] == "g0"]
    assert g0_rows["asof__clutch_efg"].isna().all()


def test_state_conditioner_frame_drops_unknown_attr_without_crash():
    out = bft.build_nba_form_state_conditioner_frame(_form(), _poe(), ["l5_pts", "not_a_real_attr"])
    assert "asof__l5_pts" in out.columns
    assert "asof__not_a_real_attr" not in out.columns


def test_builders_return_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(bft, "_FORM_SOURCE", Path("/does/not/exist.parquet"))
    assert bft._nba_form_self_cross_builder(["l5_pts"], {}) is None
    assert bft._nba_form_state_conditioner_builder(["l5_pts", "clutch_efg"], {}) is None
