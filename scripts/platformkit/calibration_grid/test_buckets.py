"""Per-file test: band edges, clamping, OT/extras collapse, never-raises fuzz.

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/calibration_grid/test_buckets.py -q
"""
from __future__ import annotations

import math

from scripts.platformkit.calibration_grid.buckets import mlb_bucket, nba_bucket, soccer_bucket


def test_nba_example_key():
    assert nba_bucket(28.0, 7, False) == "lead_+05_10|rem_12_24|reg"


def test_nba_lead_zero_and_tie_band():
    assert nba_bucket(10.0, 0, False).startswith("lead_00|")
    assert nba_bucket(10.0, 0.4, False).startswith("lead_00|")  # sub-1 magnitude clamps to tie


def test_nba_lead_band_edges():
    assert nba_bucket(0.0, 1, False).startswith("lead_+01_05|")
    assert nba_bucket(0.0, 4.9, False).startswith("lead_+01_05|")
    assert nba_bucket(0.0, 5, False).startswith("lead_+05_10|")
    assert nba_bucket(0.0, -5, False).startswith("lead_-05_10|")
    assert nba_bucket(0.0, 30, False).startswith("lead_+30_99|")
    assert nba_bucket(0.0, 500, False).startswith("lead_+30_99|")  # absurd magnitude -> top band


def test_nba_remaining_band_edges():
    assert nba_bucket(0.0, 1, False) == "lead_+01_05|rem_36_99|reg"     # rem=48
    assert nba_bucket(18.0, 1, False) == "lead_+01_05|rem_24_36|reg"    # rem=30
    assert nba_bucket(24.0, 1, False) == "lead_+01_05|rem_24_36|reg"    # rem=24, boundary->upper band
    assert nba_bucket(28.0, 1, False) == "lead_+01_05|rem_12_24|reg"    # rem=20
    assert nba_bucket(40.0, 1, False) == "lead_+01_05|rem_05_12|reg"    # rem=8
    assert nba_bucket(45.0, 1, False) == "lead_+01_05|rem_02_05|reg"    # rem=3
    assert nba_bucket(48.0, 1, False) == "lead_+01_05|rem_00_02|reg"    # rem=0


def test_nba_ot_collapses_time_segment():
    assert nba_bucket(50.0, -2, True) == "lead_-01_05|ot|ot"


def test_nba_elapsed_over_48_without_ot_flag_clamps_remaining_to_floor():
    # a caller that forgets to set is_ot never gets a negative-remaining crash
    assert nba_bucket(60.0, 1, False) == "lead_+01_05|rem_00_02|reg"


def test_mlb_example_keys():
    assert mlb_bucket(7, 3, False) == "inn_07|diff_+03|reg"
    assert mlb_bucket(11, -9, True) == "extras|diff_-06|extras"


def test_mlb_run_diff_clip_both_directions():
    assert mlb_bucket(1, 6, False) == "inn_01|diff_+06|reg"
    assert mlb_bucket(1, 999, False) == "inn_01|diff_+06|reg"
    assert mlb_bucket(1, -999, False) == "inn_01|diff_-06|reg"


def test_mlb_inning_clamped_1_to_9_when_not_extras():
    assert mlb_bucket(0, 0, False) == "inn_01|diff_+00|reg"
    assert mlb_bucket(15, 0, False) == "inn_09|diff_+00|reg"  # caller lied about extras


def test_soccer_minute_bands_and_score_diff():
    assert soccer_bucket(52.0, 1) == "min_45_60|diff_+01"
    assert soccer_bucket(0.0, 0) == "min_00_15|diff_+00"
    assert soccer_bucket(90.0, -2) == "min_75_99|diff_-02"


def test_soccer_unknown_score_band():
    assert soccer_bucket(52.0, None) == "min_45_60|score_unknown"


def test_soccer_score_diff_clipped():
    assert soccer_bucket(1.0, 999) == "min_00_15|diff_+05"
    assert soccer_bucket(1.0, -999) == "min_00_15|diff_-05"


def _weird_values():
    return [float("nan"), float("inf"), float("-inf"), -1.0, 0, "", None, 1e300, -1e300]


def test_never_raises_fuzz_nba():
    for v in _weird_values():
        for lead in _weird_values():
            for ot in (True, False):
                assert isinstance(nba_bucket(v, lead, ot), str)


def test_never_raises_fuzz_mlb():
    for v in _weird_values():
        for diff in _weird_values():
            for ex in (True, False):
                assert isinstance(mlb_bucket(v, diff, ex), str)


def test_never_raises_fuzz_soccer():
    for v in _weird_values():
        for diff in list(_weird_values()) + [None]:
            assert isinstance(soccer_bucket(v, diff), str)


def test_deterministic_same_inputs_same_key():
    assert nba_bucket(24.0, 7, False) == nba_bucket(24.0, 7, False)
    assert mlb_bucket(7, 3, False) == mlb_bucket(7, 3, False)
    assert soccer_bucket(52.0, 1) == soccer_bucket(52.0, 1)


if __name__ == "__main__":
    test_nba_example_key()
    test_never_raises_fuzz_nba()
    test_never_raises_fuzz_mlb()
    test_never_raises_fuzz_soccer()
    print("ok")
