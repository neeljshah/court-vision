"""Per-file tests for pitch_engine.corpus -- mappings, buckets, PA extraction."""
import numpy as np
import pandas as pd

from domains.mlb.pitch_engine import corpus as C


def test_pitch_class_and_outcome_maps():
    pt = pd.Series(["FF", "SL", "CH", "PO"])
    assert C.pitch_class(pt).tolist() == ["FB", "BR", "OS", None]
    desc = pd.Series(["ball", "called_strike", "swinging_strike", "foul",
                      "hit_into_play", "hit_into_play", "hit_by_pitch"])
    ev = pd.Series([None, None, None, None, "single", "field_out", "hit_by_pitch"])
    assert C.pitch_outcome(desc, ev).tolist() == [
        "ball", "called_strike", "swinging_strike", "foul",
        "single", "in_play_out", "hbp"]


def test_pa_event_and_buckets():
    ev = pd.Series(["field_out", "strikeout", "walk", "home_run", "grounded_into_double_play"])
    assert C.pa_event(ev).tolist() == ["OUT", "K", "BB", "HR", "OUT"]
    assert C.count_idx([0, 3, 2], [0, 2, 1]).tolist() == [0, 11, 7]
    # platoon RR=0, RL=1, LR=2, LL=3
    assert C.platoon_idx(pd.Series(["R", "R", "L", "L"]),
                         pd.Series(["R", "L", "R", "L"])).tolist() == [0, 1, 2, 3]
    bits = np.array([0, 1, 2, 5])   # empty, 1B, 2B, 1B+3B
    assert C.base_bucket_from_bits(bits).tolist() == [0, 1, 2, 2]


def test_build_pa_frame_runs():
    # a 2-pitch PA (Bot half, home batting) ending in a 2-run play
    df = pd.DataFrame({
        "game_pk": [1, 1], "inning": [1, 1], "inning_topbot": ["Bot", "Bot"],
        "at_bat_number": [1, 1], "pitch_number": [1, 2],
        "pitcher": [10, 10], "batter": [20, 20],
        "events": [None, "double"], "description": ["ball", "hit_into_play"],
        "pitch_type": ["FF", "FF"], "balls": [0, 1], "strikes": [0, 0],
        "outs_when_up": [1, 1], "on_1b": [np.nan, np.nan],
        "on_2b": [np.nan, np.nan], "on_3b": [np.nan, np.nan],
        "bat_score": [3, 3], "post_home_score": [5, 5], "post_away_score": [0, 0],
        "stand": ["R", "R"], "p_throws": ["R", "R"], "zone": [5, 5],
    })
    # build_pa_frame consumes an already-loaded pitch frame; pclass is attached
    # by load_pitch_frame in production -- set it here to exercise build_pa_frame.
    df["pclass"] = "FB"
    pa = C.build_pa_frame(df)
    assert len(pa) == 1
    row = pa.iloc[0]
    assert row["pa_evt"] == "2B"
    assert row["runs"] == 2          # post_home 5 - bat_score 3
    assert row["base_out_state"] == 1    # empty bases (0) * 3 + outs 1
