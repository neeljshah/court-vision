"""Per-file test for interaction_factory.builders_nba_lineup (B7 lane).
Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_nba_lineup.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.interaction_factory import builders_nba_lineup as bnl
from scripts.platformkit.interaction_factory import generator as GEN


# --------------------------------------------------------------------------
# 1. Template registration shape.
def test_self_cross_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["nba_onoff_self_cross"]
    assert tpl["sport"] == "basketball_nba"
    assert tpl["atomic_unit"] == "player_game"
    assert tpl["outcome"] == "efg"
    assert tpl["pairing"] == "self_cross"
    assert tpl["left_pool"] == {"static_pool": "nba_onoff_asof"}
    assert tpl["feature_builder"] == "nba_onoff_self_cross_asof"


def test_state_conditioner_template_registered_with_expected_shape():
    tpl = GEN.TEMPLATES["nba_onoff_state_conditioner"]
    assert tpl["sport"] == "basketball_nba"
    assert tpl["atomic_unit"] == "player_game"
    assert tpl["outcome"] == "efg"
    assert tpl["pairing"] == "cross"
    assert tpl["left_pool"] == {"static_pool": "nba_onoff_asof"}
    assert tpl["right_pool"] == {"attributes": ["late_clock_efg", "clutch_efg"]}
    assert tpl["feature_builder"] == "nba_onoff_state_conditioner_asof"


def test_static_pool_has_3_onoff_cols():
    pool = GEN.STATIC_POOLS["nba_onoff_asof"]
    assert pool == ["onoff_net_on_asof", "onoff_net_off_asof", "onoff_min_share_asof"]


def test_builders_registered_in_runner():
    from scripts.platformkit.interaction_factory import runner as RUN
    assert RUN._BUILDERS["nba_onoff_self_cross_asof"] is bnl._nba_onoff_self_cross_builder
    assert RUN._BUILDERS["nba_onoff_state_conditioner_asof"] is bnl._nba_onoff_state_conditioner_builder


# --------------------------------------------------------------------------
# 2. Candidate enumeration non-empty (C(3,2)=3 self-cross, 3*2=6 conditioner).
def test_self_cross_enumeration_nonempty():
    cands = GEN.enumerate_candidates("nba_onoff_self_cross")
    assert len(cands) == 3
    assert all(isinstance(c, GEN.Candidate) for c in cands)
    assert all(c.feature_builder == "nba_onoff_self_cross_asof" for c in cands)


def test_state_conditioner_enumeration_nonempty():
    cands = GEN.enumerate_candidates("nba_onoff_state_conditioner")
    assert len(cands) == 6
    pairs = {(c.attr_a, c.attr_b) for c in cands}
    assert ("onoff_net_on_asof", "late_clock_efg") in pairs
    assert ("onoff_min_share_asof", "clutch_efg") in pairs


# --------------------------------------------------------------------------
# 3. build_onoff_game_rows: explode lineup_key into per-player on/off game rows.
def _stints():
    # team 100, game g0: 2 clean stints. Lineup A (players 1,2,3,4,5) plays
    # 1000s scoring 10-6, then subs to lineup B (1,2,3,4,6) for 620s
    # scoring 4-4. Player 5's on_secs=1000, player 6's on_secs=620, players
    # 1-4 on_secs=1620 (full game), team_secs=1620.
    return pd.DataFrame({
        "game_id": ["g0", "g0"],
        "team_id": [100, 100],
        "period": [1, 1],
        "lineup_key": ["1,2,3,4,5", "1,2,3,4,6"],
        "n_on_court": [5, 5],
        "start_s": [0.0, 1000.0],
        "end_s": [1000.0, 1620.0],
        "elapsed_s": [1000.0, 620.0],
        "pts_for": [10, 4],
        "pts_against": [6, 4],
        "quality": ["", ""],
    })


def test_build_onoff_game_rows_explodes_and_computes_off_as_team_minus_on():
    out = bnl.build_onoff_game_rows(_stints())
    assert set(out["player_id"]) == {1, 2, 3, 4, 5, 6}
    p1 = out[out["player_id"] == 1].iloc[0]
    assert p1["on_secs"] == 1620.0
    assert p1["off_secs"] == 0.0
    p5 = out[out["player_id"] == 5].iloc[0]
    assert p5["on_secs"] == 1000.0
    assert p5["off_secs"] == 620.0
    assert p5["on_pts_for"] == 10 and p5["on_pts_against"] == 6
    assert p5["off_pts_for"] == 4 and p5["off_pts_against"] == 4


def test_build_onoff_game_rows_drops_dirty_stints():
    dirty = _stints().copy()
    dirty.loc[0, "n_on_court"] = 4
    out = bnl.build_onoff_game_rows(dirty)
    assert 5 not in set(out["player_id"])  # only appeared in the dropped dirty stint


# --------------------------------------------------------------------------
# 4. build_onoff_asof: strictly-prior cumsum-shift, leak trap.
def _two_game_stints():
    """Player 1 on team 100 for 2 games: g0 (2024-11-01) on-court whole game
    scoring +10 net over 1200s, g1 (2024-11-03) on-court whole game."""
    return pd.DataFrame({
        "game_id": ["g0", "g1"],
        "team_id": [100, 100],
        "period": [1, 1],
        "lineup_key": ["1,2,3,4,5", "1,2,3,4,5"],
        "n_on_court": [5, 5],
        "start_s": [0.0, 0.0],
        "end_s": [1200.0, 1200.0],
        "elapsed_s": [1200.0, 1200.0],
        "pts_for": [20, 15],
        "pts_against": [10, 15],
        "quality": ["", ""],
    })


def _games():
    return pd.DataFrame({
        "game_id": ["g0", "g1"],
        "date": pd.to_datetime(["2024-11-01", "2024-11-03"]),
    })


def test_build_onoff_asof_leak_trap_first_game_is_nan_second_uses_only_g0():
    out = bnl.build_onoff_asof(_two_game_stints(), _games(), min_prior_seconds=100)
    g0 = out[out["game_id"] == "g0"]
    assert g0["onoff_net_on_asof"].isna().all()  # no prior games -> NaN, never fabricated
    g1 = out[(out["game_id"] == "g1") & (out["player_id"] == 1)].iloc[0]
    # strictly-prior: only g0's (20-10)/1200*2880 = 24.0, g1's OWN +0 net never leaks in
    assert abs(g1["onoff_net_on_asof"] - 24.0) < 1e-9
    assert g1["onoff_min_share_asof"] == 1.0  # on 100% of team's accounted secs in g0


def test_build_onoff_asof_min_prior_seconds_gate():
    out = bnl.build_onoff_asof(_two_game_stints(), _games(), min_prior_seconds=99999)
    assert out["onoff_net_on_asof"].isna().all()
    assert out["onoff_net_off_asof"].isna().all()


# --------------------------------------------------------------------------
# 5. Frame builders: synthetic onoff_asof + player_offense_events.
def _onoff():
    return pd.DataFrame({
        "player_id": [1, 1],
        "game_id": ["g0", "g1"],
        "onoff_net_on_asof": [float("nan"), 24.0],
        "onoff_net_off_asof": [float("nan"), -5.0],
        "onoff_min_share_asof": [float("nan"), 1.0],
    })


def _poe():
    return pd.DataFrame({
        "player_id": [1, 1],
        "game_id": ["g0", "g1"],
        "date": pd.to_datetime(["2024-11-01", "2024-11-03"]),
        "total_fgm": [8, 10], "total_fga": [16, 18],
        "above_break_3_fgm": [2, 3], "corner3_fgm": [0, 0],
        "late_clock_fgm": [1, 2], "late_clock_fga": [2, 3], "late_clock_fg3m": [0, 1],
        "clutch_fgm": [1, 1], "clutch_fga": [2, 2], "clutch_fg3m": [0, 0],
    })


def test_self_cross_frame_sets_y_and_asof_cols():
    out = bnl.build_nba_onoff_self_cross_frame(_onoff(), _poe(), ["onoff_net_on_asof", "onoff_min_share_asof"])
    assert {"asof__onoff_net_on_asof", "asof__onoff_min_share_asof", "y"} <= set(out.columns)
    assert len(out) == 2
    row = out[out["game_id"] == "g1"].iloc[0]
    assert abs(row["y"] - (10 + 0.5 * 3) / 18) < 1e-9
    assert row["asof__onoff_net_on_asof"] == 24.0
    g0_row = out[out["game_id"] == "g0"].iloc[0]
    assert pd.isna(g0_row["asof__onoff_net_on_asof"])  # first game -- never fabricated


def test_state_conditioner_frame_has_onoff_and_state_cols():
    out = bnl.build_nba_onoff_state_conditioner_frame(
        _onoff(), _poe(), ["onoff_net_on_asof", "clutch_efg"], min_prior_att=1)
    assert {"asof__onoff_net_on_asof", "asof__clutch_efg", "y"} <= set(out.columns)
    row = out[out["game_id"] == "g1"].iloc[0]
    assert abs(row["asof__clutch_efg"] - 0.5) < 1e-9  # g0's 1fgm/2fga, no 3s = 0.5, strictly prior


def test_state_conditioner_frame_drops_unknown_attr_without_crash():
    out = bnl.build_nba_onoff_state_conditioner_frame(_onoff(), _poe(), ["onoff_net_on_asof", "not_a_real_attr"])
    assert "asof__onoff_net_on_asof" in out.columns
    assert "asof__not_a_real_attr" not in out.columns


def test_builders_return_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(bnl, "_STINTS_DIR", Path("/does/not/exist"))
    assert bnl._nba_onoff_self_cross_builder(["onoff_net_on_asof"], {}) is None
    assert bnl._nba_onoff_state_conditioner_builder(["onoff_net_on_asof", "clutch_efg"], {}) is None
