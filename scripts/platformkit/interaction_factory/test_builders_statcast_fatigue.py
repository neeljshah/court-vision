"""Per-file test for interaction_factory.builders_statcast_fatigue (B1).
Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_statcast_fatigue.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.interaction_factory import builders_statcast_fatigue as bsf
from scripts.platformkit.interaction_factory import generator as GEN


# --------------------------------------------------------------------------
# 1. Template + STATIC_POOL registration shape.
def test_templates_registered_with_expected_shape():
    self_cross = GEN.TEMPLATES["mlb_sp_ingame_fatigue_self_cross"]
    assert self_cross["sport"] == "mlb"
    assert self_cross["pairing"] == "self_cross"
    assert self_cross["outcome"] == "rest_of_appearance_xwoba"
    assert self_cross["left_pool"] == {"static_pool": "mlb_sp_ingame_fatigue_state"}
    assert self_cross["feature_builder"] == "mlb_sp_ingame_fatigue_asof"

    cond = GEN.TEMPLATES["mlb_sp_fatigue_state_conditioner"]
    assert cond["pairing"] == "cross"
    assert cond["left_pool"] == {"static_pool": "mlb_sp_fatigue_prior"}
    assert cond["right_pool"] == {"static_pool": "mlb_sp_ingame_fatigue_state"}
    assert cond["feature_builder"] == "mlb_sp_fatigue_state_conditioner_asof"


def test_builders_registered_in_runner():
    from scripts.platformkit.interaction_factory import runner as RUN
    assert RUN._BUILDERS["mlb_sp_ingame_fatigue_asof"] is bsf._mlb_sp_ingame_fatigue_builder
    assert RUN._BUILDERS["mlb_sp_fatigue_state_conditioner_asof"] is bsf._mlb_sp_fatigue_state_conditioner_builder


def test_enumeration_nonempty_for_both_templates():
    self_cross = GEN.enumerate_candidates("mlb_sp_ingame_fatigue_self_cross")
    assert len(self_cross) > 0
    assert all(isinstance(c, GEN.Candidate) for c in self_cross)
    cond = GEN.enumerate_candidates("mlb_sp_fatigue_state_conditioner")
    assert len(cond) > 0
    pairs = {(c.attr_a, c.attr_b) for c in cond}
    assert ("woba_tto3_minus_tto1", "velo_delta_by_pitch_count") in pairs


# --------------------------------------------------------------------------
# 2. Checkpoint frame: one pitcher, one appearance, 20 baseline-ish pitches
# then more -- velo rises after pitch 15 (fatigue-like), spin flat, extension
# always absent (NaN, honest). Checkpoint fixed at k=18 (below CHECKPOINTS'
# real values, injected directly to keep the fixture small).
def _synthetic_appearance(n_pitches=25, velo_late_bump=2.0):
    rows = []
    for i in range(1, n_pitches + 1):
        ab = 1 + (i - 1) // 5   # 5 pitches/PA
        velo = 95.0 + (velo_late_bump if i > bsf.BASELINE_PITCHES else 0.0)
        rows.append({
            "game_pk": 1, "game_date": "2023-04-01", "at_bat_number": ab, "pitch_number": ((i - 1) % 5) + 1,
            "pitcher": 100, "batter": 200 + ab, "release_speed": velo, "release_spin_rate": 2200.0,
            "estimated_woba_using_speedangle": 0.300 if i % 5 == 0 else None,
        })
    return pd.DataFrame(rows)


def test_checkpoint_frame_shape_and_velo_delta():
    frame = bsf.build_mlb_fatigue_checkpoint_frame(
        _synthetic_appearance(), ["velo_delta_by_pitch_count", "spin_delta_by_pitch_count",
                                    "release_extension_delta", "times_through_order"],
        checkpoints=(18,))
    assert len(frame) == 1
    row = frame.iloc[0]
    # baseline = mean(pitches 1-15) = 95.0; window 1-18 mean = (15*95 + 3*97)/18
    expected = (15 * 95.0 + 3 * 97.0) / 18 - 95.0
    assert abs(row["asof__velo_delta_by_pitch_count"] - expected) < 1e-9
    assert abs(row["asof__spin_delta_by_pitch_count"] - 0.0) < 1e-9
    # release_extension is absent from the source -> honestly NaN, never invented.
    assert pd.isna(row["asof__release_extension_delta"])
    assert row["asof__times_through_order"] in (1.0, 2.0, 3.0)


def test_checkpoint_missing_all_attrs_returns_empty_asof_columns_without_crash():
    frame = bsf.build_mlb_fatigue_checkpoint_frame(_synthetic_appearance(), ["not_a_real_attr"], checkpoints=(18,))
    assert list(frame.columns) == ["game_pk", "pitcher", "checkpoint", "y"]
    assert len(frame) == 1


def test_checkpoint_never_reached_drops_row_honestly():
    frame = bsf.build_mlb_fatigue_checkpoint_frame(
        _synthetic_appearance(n_pitches=10), ["velo_delta_by_pitch_count"], checkpoints=(18,))
    assert len(frame) == 0   # appearance never reached pitch 18 -- no invented row


# --------------------------------------------------------------------------
# 3. LEAK-GUARD (mandatory shifted-cumsum trap test): a checkpoint-k row must
# be identical whether or not pitches AFTER k exist / change.
def test_checkpoint_trap_pitches_after_k_never_leak_in():
    base = _synthetic_appearance(n_pitches=20)
    frame_a = bsf.build_mlb_fatigue_checkpoint_frame(base, ["velo_delta_by_pitch_count"], checkpoints=(18,))
    # mutate every pitch strictly AFTER checkpoint 18 (pitches 19-20) to an extreme value.
    tampered = base.copy()
    tampered.loc[tampered["pitch_number"].notna() & (tampered.index >= 18), "release_speed"] = 999.0
    frame_b = bsf.build_mlb_fatigue_checkpoint_frame(tampered, ["velo_delta_by_pitch_count"], checkpoints=(18,))
    assert abs(frame_a.iloc[0]["asof__velo_delta_by_pitch_count"]
               - frame_b.iloc[0]["asof__velo_delta_by_pitch_count"]) < 1e-9


def test_checkpoint_outcome_excludes_pitches_up_to_and_including_k():
    # y = mean xwoba strictly AFTER k=18: only pitch 20 (i%5==0, i=20) qualifies -> 0.300.
    frame = bsf.build_mlb_fatigue_checkpoint_frame(_synthetic_appearance(), ["velo_delta_by_pitch_count"],
                                                     checkpoints=(18,))
    assert abs(frame.iloc[0]["y"] - 0.300) < 1e-9


# --------------------------------------------------------------------------
# 4. Prior-games frame: same pitcher, 2 chronological games. Game 2's prior
# split must reflect ONLY game 1's PAs -- the mandatory cross-game trap test.
def _two_game_pa_df():
    rows = []
    # Game 1 (2023-04-01): 3 PAs vs 3 different batters -> all TTO1, xwoba .200/.400/.600
    for ab, xwoba in enumerate([0.200, 0.400, 0.600], start=1):
        rows.append({"game_pk": 1, "game_date": "2023-04-01", "at_bat_number": ab, "pitch_number": 1,
                      "pitcher": 5, "batter": 100 + ab, "release_speed": 95.0, "release_spin_rate": 2200.0,
                      "estimated_woba_using_speedangle": xwoba})
    # Game 2 (2023-04-08): 1 PA, TTO1 (new batter) -> should NOT affect its own prior.
    rows.append({"game_pk": 2, "game_date": "2023-04-08", "at_bat_number": 1, "pitch_number": 1,
                 "pitcher": 5, "batter": 999, "release_speed": 95.0, "release_spin_rate": 2200.0,
                 "estimated_woba_using_speedangle": 0.900})
    return pd.DataFrame(rows)


def test_prior_frame_uses_only_strictly_prior_games():
    frame = bsf.build_mlb_fatigue_prior_frame(_two_game_pa_df(), min_prior_pa=1)
    frame = frame.set_index("game_pk")
    # game 1 has no prior games -> undefined (no TTO3 bucket ever reached either).
    assert pd.isna(frame.loc[1, "asof__woba_tto3_minus_tto1"])
    # game 2's prior TTO1 rate = mean(.200,.400,.600) = .400 from game 1 only;
    # no TTO3 PAs exist anywhere -> tto3 side stays NaN -> delta NaN (never invented).
    assert pd.isna(frame.loc[2, "asof__woba_tto3_minus_tto1"])


def test_prior_frame_trap_todays_own_pa_never_leaks_into_todays_row():
    d1 = _two_game_pa_df()
    d2 = d1.copy()
    # tamper game 2's own PA outcome -- game 2's prior (built from game 1 only) must be unchanged.
    d2.loc[d2["game_pk"] == 2, "estimated_woba_using_speedangle"] = -5.0
    f1 = bsf.build_mlb_fatigue_prior_frame(d1, min_prior_pa=1).set_index("game_pk")
    f2 = bsf.build_mlb_fatigue_prior_frame(d2, min_prior_pa=1).set_index("game_pk")
    a, b = f1.loc[2, "asof__woba_tto3_minus_tto1"], f2.loc[2, "asof__woba_tto3_minus_tto1"]
    assert (pd.isna(a) and pd.isna(b)) or abs(a - b) < 1e-9


# --------------------------------------------------------------------------
# 5. State-conditioner builder: merges the prior frame onto the checkpoint
# frame keyed (game_pk, pitcher) -- both asof__ families present, no crash.
def test_state_conditioner_builder_merges_both_families(monkeypatch):
    # decoupled from real statcast files on disk: _STATCAST_SOURCES only needs
    # to point at SOMETHING that exists (the exists() guard, never read --
    # read_combined_source is mocked below) + the mock supplies the frame.
    monkeypatch.setattr(bsf, "_STATCAST_SOURCES", (Path(__file__),))
    # n_pitches=35 so the appearance clears CHECKPOINTS' first real value (30)
    # -- the wrapper builder uses the module-default checkpoints, unlike the
    # other tests here which inject a small checkpoints=(18,) directly.
    monkeypatch.setattr(bsf, "read_combined_source", lambda sources=None: _synthetic_appearance(n_pitches=35))
    out = bsf._mlb_sp_fatigue_state_conditioner_builder(
        ["woba_tto3_minus_tto1", "velo_delta_by_pitch_count"], {})
    assert out is not None
    frame = out["frame"]
    assert "asof__velo_delta_by_pitch_count" in frame.columns
    assert "asof__woba_tto3_minus_tto1" in frame.columns
    assert out["cluster"] == "pitcher"


# --------------------------------------------------------------------------
# 6. Missing-source -> None, no crash (both builders).
def test_builders_return_none_when_source_missing(monkeypatch):
    monkeypatch.setattr(bsf, "_STATCAST_SOURCES", (Path("/does/not/exist_2022.parquet"),
                                                      Path("/does/not/exist_2023.parquet")))
    assert bsf._mlb_sp_ingame_fatigue_builder(["velo_delta_by_pitch_count"], {}) is None
    assert bsf._mlb_sp_fatigue_state_conditioner_builder(["woba_tto3_minus_tto1"], {}) is None
