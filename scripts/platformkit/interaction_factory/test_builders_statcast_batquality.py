"""Per-file test for interaction_factory.builders_statcast_batquality (B2).
Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_statcast_batquality.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.interaction_factory import builders_statcast_batquality as bsq
from scripts.platformkit.interaction_factory import builders_statcast_fatigue as bsf
from scripts.platformkit.interaction_factory import generator as GEN


# --------------------------------------------------------------------------
# 1. Template + STATIC_POOL registration shape.
def test_templates_registered_with_expected_shape():
    self_cross = GEN.TEMPLATES["mlb_batquality_self_cross"]
    assert self_cross["sport"] == "mlb"
    assert self_cross["pairing"] == "self_cross"
    assert self_cross["outcome"] == "bip_launch_speed"
    assert self_cross["left_pool"] == {"static_pool": "mlb_batquality_prior"}
    assert self_cross["feature_builder"] == "mlb_batquality_asof"

    cond = GEN.TEMPLATES["mlb_batquality_state_conditioner"]
    assert cond["pairing"] == "cross"
    assert cond["left_pool"]["static_pool"] == "mlb_batquality_prior"
    assert cond["right_pool"] == {"static_pool": "mlb_sp_ingame_fatigue_state"}
    assert cond["feature_builder"] == "mlb_batquality_state_conditioner_asof"

    pool = set(GEN.STATIC_POOLS["mlb_batquality_prior"])
    assert pool == {
        "batter_ev_mean_asof_30d", "batter_ev_mean_asof_season",
        "batter_barrel_rate_asof_30d", "batter_barrel_rate_asof_season",
        "batter_la_sweetspot_asof_30d", "batter_la_sweetspot_asof_season",
        "pitcher_ev_allowed_asof_30d", "pitcher_ev_allowed_asof_season",
    }


def test_builders_registered_in_runner():
    from scripts.platformkit.interaction_factory import runner as RUN
    assert RUN._BUILDERS["mlb_batquality_asof"] is bsq._mlb_batquality_self_cross_builder
    assert RUN._BUILDERS["mlb_batquality_state_conditioner_asof"] is bsq._mlb_batquality_state_conditioner_builder


def test_enumeration_nonempty_for_both_templates():
    self_cross = GEN.enumerate_candidates("mlb_batquality_self_cross")
    assert len(self_cross) > 0
    assert all(isinstance(c, GEN.Candidate) for c in self_cross)

    cond = GEN.enumerate_candidates("mlb_batquality_state_conditioner")
    assert len(cond) > 0
    # left pool narrowed via `exclude` to just the 2 pitcher windows -- the
    # batter-side attrs have no atomic-unit-compatible checkpoint row to key on.
    left_attrs = {c.attr_a for c in cond}
    assert left_attrs == {"pitcher_ev_allowed_asof_30d", "pitcher_ev_allowed_asof_season"}
    pairs = {(c.attr_a, c.attr_b) for c in cond}
    assert ("pitcher_ev_allowed_asof_30d", "velo_delta_by_pitch_count") in pairs


# --------------------------------------------------------------------------
# 2. barrel / sweet-spot definition unit test on a tiny fixture.
def test_barrel_and_sweetspot_definitions():
    ev = pd.Series([99.0, 99.0, 80.0, 99.0, None])
    la = pd.Series([28.0, 10.0, 28.0, None, 28.0])
    barrel = bsq.is_barrel(ev, la)
    # row0: EV99 & LA28 in [26,30] -> barrel; row1: EV99 & LA10 outside the band -> not;
    # row2: EV80 (<98) -> not; row3: LA missing -> NaN; row4: EV missing -> NaN.
    assert barrel.iloc[0]
    assert not barrel.iloc[1]
    assert not barrel.iloc[2]
    assert pd.isna(barrel.iloc[3])
    assert pd.isna(barrel.iloc[4])

    sweet = bsq.is_sweetspot(la)
    assert sweet.iloc[0]   # LA28 in [8,32]
    assert sweet.iloc[1]   # LA10 in [8,32]
    assert sweet.iloc[2]   # LA28 in [8,32]
    assert pd.isna(sweet.iloc[3])   # LA missing -> honest NaN, never invented


# --------------------------------------------------------------------------
# 3. windowing correctness + mandatory leak trap, via _entity_game_agg +
# _asof_metric directly (min_n=1, bypassing MIN_PRIOR_N=10 for a tiny fixture).
def _bip_fixture() -> pd.DataFrame:
    # one batter (id=1), one pitcher (id=9), 3 chronological games.
    rows = [
        # game 1 (2023-04-01): ev 90, 100 -> mean 95
        {"game_pk": 1, "game_date": "2023-04-01", "at_bat_number": 1, "pitcher": 9, "batter": 1,
         "launch_speed": 90.0, "launch_angle": 10.0},
        {"game_pk": 1, "game_date": "2023-04-01", "at_bat_number": 2, "pitcher": 9, "batter": 1,
         "launch_speed": 100.0, "launch_angle": 15.0},
        # game 2 (2023-04-10, 9 days later -- inside a later game's 30d window): ev 110
        {"game_pk": 2, "game_date": "2023-04-10", "at_bat_number": 1, "pitcher": 9, "batter": 1,
         "launch_speed": 110.0, "launch_angle": 20.0},
        # game 3 (2023-05-20, 40 days after game 2 -- OUTSIDE the 30d window of game1/game2)
        {"game_pk": 3, "game_date": "2023-05-20", "at_bat_number": 1, "pitcher": 9, "batter": 1,
         "launch_speed": 70.0, "launch_angle": 5.0},
    ]
    return pd.DataFrame(rows)


def test_asof_windows_season_and_30d_strictly_prior():
    bip = bsq._prep_bip(_bip_fixture())
    game = bsq._entity_game_agg(bip, "batter")
    out = bsq._asof_metric(game, "batter", "sum_ev", "n_ev", "batter_ev_mean_asof", min_n=1).set_index("game_pk")
    # game 1: no prior games -> NaN both windows.
    assert pd.isna(out.loc[1, "asof__batter_ev_mean_asof_season"])
    assert pd.isna(out.loc[1, "asof__batter_ev_mean_asof_30d"])
    # game 2: prior = game 1 only (mean of 90,100 = 95), 9 days -> inside 30d too.
    assert abs(out.loc[2, "asof__batter_ev_mean_asof_season"] - 95.0) < 1e-9
    assert abs(out.loc[2, "asof__batter_ev_mean_asof_30d"] - 95.0) < 1e-9
    # game 3: season prior = mean(90,100,110) = 100 (games 1+2); 30d prior excludes
    # both (40/49 days back) -> NaN, honest, never invented.
    assert abs(out.loc[3, "asof__batter_ev_mean_asof_season"] - 100.0) < 1e-9
    assert pd.isna(out.loc[3, "asof__batter_ev_mean_asof_30d"])


def test_asof_trap_todays_own_bip_never_leaks_into_todays_row():
    base = _bip_fixture()
    tampered = base.copy()
    tampered.loc[tampered["game_pk"] == 2, "launch_speed"] = 999.0
    out1 = bsq._asof_metric(bsq._entity_game_agg(bsq._prep_bip(base), "batter"),
                             "batter", "sum_ev", "n_ev", "batter_ev_mean_asof", min_n=1).set_index("game_pk")
    out2 = bsq._asof_metric(bsq._entity_game_agg(bsq._prep_bip(tampered), "batter"),
                             "batter", "sum_ev", "n_ev", "batter_ev_mean_asof", min_n=1).set_index("game_pk")
    # game 2's OWN asof row must be unaffected by tampering game 2's OWN value.
    assert abs(out1.loc[2, "asof__batter_ev_mean_asof_season"]
               - out2.loc[2, "asof__batter_ev_mean_asof_season"]) < 1e-9
    assert abs(out1.loc[2, "asof__batter_ev_mean_asof_30d"]
               - out2.loc[2, "asof__batter_ev_mean_asof_30d"]) < 1e-9


# --------------------------------------------------------------------------
# 4. PA-level self-cross frame: shape, cluster column present, real same-PA y.
def test_pa_frame_shape_and_cluster_column():
    frame = bsq.build_mlb_batquality_pa_frame(
        _bip_fixture(), ["batter_ev_mean_asof_season", "pitcher_ev_allowed_asof_season"])
    assert "batter" in frame.columns   # cluster column, must be a plain frame column
    assert "y" in frame.columns
    assert "asof__batter_ev_mean_asof_season" in frame.columns
    assert "asof__pitcher_ev_allowed_asof_season" in frame.columns
    g1 = frame[frame["game_pk"] == 1].sort_values("at_bat_number")
    assert list(g1["y"]) == [90.0, 100.0]   # y = THIS PA's own realized launch_speed


# --------------------------------------------------------------------------
# 5. missing-source -> None, no crash (both builders).
def test_builders_return_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(bsq, "_STATCAST_SOURCES", (Path("/does/not/exist_2022.parquet"),
                                                      Path("/does/not/exist_2023.parquet")))
    assert bsq._mlb_batquality_self_cross_builder(["batter_ev_mean_asof_season"], {}) is None
    assert bsq._mlb_batquality_state_conditioner_builder(["pitcher_ev_allowed_asof_season"], {}) is None


# --------------------------------------------------------------------------
# 6. State-conditioner builder: merges the pitcher batted-ball-quality prior
# onto the fatigue checkpoint frame -- both asof__ families present, no crash.
def _fatigue_synth_appearance(n_pitches=35, game_pk=2, pitcher=9) -> pd.DataFrame:
    rows = []
    for i in range(1, n_pitches + 1):
        ab = 1 + (i - 1) // 5
        rows.append({
            "game_pk": game_pk, "game_date": "2023-04-10", "at_bat_number": ab, "pitch_number": ((i - 1) % 5) + 1,
            "pitcher": pitcher, "batter": 200 + ab, "release_speed": 95.0, "release_spin_rate": 2200.0,
            "estimated_woba_using_speedangle": 0.300 if i % 5 == 0 else None,
        })
    return pd.DataFrame(rows)


def test_state_conditioner_builder_merges_both_families(monkeypatch):
    monkeypatch.setattr(bsq, "_STATCAST_SOURCES", (Path(__file__),))
    monkeypatch.setattr(bsq, "read_combined_source", lambda sources=None: _bip_fixture())
    monkeypatch.setattr(bsf, "read_combined_source", lambda sources=None: _fatigue_synth_appearance())
    out = bsq._mlb_batquality_state_conditioner_builder(
        ["pitcher_ev_allowed_asof_season", "velo_delta_by_pitch_count"], {})
    assert out is not None
    frame = out["frame"]
    assert "asof__velo_delta_by_pitch_count" in frame.columns
    assert "asof__pitcher_ev_allowed_asof_season" in frame.columns
    assert out["cluster"] == "pitcher"
