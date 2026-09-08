"""G322 CONSTRUCT test -- hand-computed box_h / cut / share / selection arithmetic. n = 1 (CONSTRUCT).

Run ONLY this file: python -m pytest tests/platformkit/test_g322_oversized_boxes.py -q
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.platformkit.tracking.g322_oversized_boxes import (  # noqa: E402
    _share, census_game, decile_ranks, panel_rows, pick_panel_games,
)

HEADER = ["frame", "player_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
          "confidence", "source_height"]
# frame_h = 100 everywhere; box_h = 60, 40, 30, (bad), 90
ROWS = [
    [1, "a", 0, 10, 20, 70, 0.5, 100],      # box_h 60 -> >50, >33, >25
    [2, "b", 0, 0, 20, 40, 0.5, 100],       # box_h 40 -> >33, >25
    [3, "c", 0, 0, 20, 30, 0.5, 100],       # box_h 30 -> >25 only
    [4, "d", 0, "", 20, 55, 0.5, 100],      # unusable -> rows_bad
    [5, "e", 0, 5, 20, 95, 1.0, 100],       # box_h 90 -> >50, >33, >25, matched
]


def _table(tmp_path):
    p = tmp_path / "tracking_data.csv"
    with open(p, "w", newline="", encoding="ascii") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        for r in ROWS:
            w.writerow(r)
    return str(p)


def test_census_counts_are_hand_computed(tmp_path):
    a = census_game(_table(tmp_path))
    assert (a["rows_total"], a["rows_bad"], a["rows_valid"]) == (5, 1, 4)
    assert (a["n_gt50"], a["n_gt33"], a["n_gt25"]) == (2, 3, 4)
    # post-TOPCUT denominator is 100 - 60 = 40, so the cut is 20: all four clear it
    assert a["n_gt50_posttopcut"] == 4
    # PAD removed: box_h - 30 > 50 holds only for the 90 px box
    assert a["n_gt50_padremoved"] == 1
    assert (a["n_matched"], a["n_gt50_matched"]) == (1, 1)
    assert (a["n_coasting"], a["n_gt50_coasting"]) == (3, 1)
    assert (a["max_bbox_y2"], a["max_box_h"]) == (95.0, 90.0)
    assert a["table_source_height"] == 100.0 and a["height_disagrees"] == 0


def test_panel_rows_are_above_cut_and_sorted(tmp_path):
    pr = panel_rows(_table(tmp_path))
    assert [r["box_h"] for r in pr] == [60.0, 90.0]
    assert [r["ratio"] for r in pr] == [0.6, 0.9]


def test_decile_ranks_are_the_odd_decile_midpoints():
    assert decile_ranks(100) == [10, 30, 50, 70, 90]
    assert decile_ranks(10) == [1, 3, 5, 7, 9]
    assert decile_ranks(3) == [1, 1, 2, 3, 3]
    assert decile_ranks(1) == [1, 1, 1, 1, 1]


def test_pick_panel_games_takes_medians_then_the_maximum():
    def g(gid, res, n50, rows_valid=1000):
        return {"game_id": gid, "source_resolution": res,
                "n_gt50": n50, "rows_valid": rows_valid}
    rows = [
        g("hd_lo", "1920x1080", 100), g("hd_mid", "1920x1080", 200), g("hd_hi", "1920x1080", 300),
        g("sd_lo", "1280x720", 400), g("sd_hi", "1280x720", 500),
        g("lo_only", "640x360", 600),
        g("ineligible", "640x360", 99, rows_valid=100),   # below ELIGIBLE_MIN -> never picked
    ]
    assert pick_panel_games(rows) == ["hd_mid", "sd_lo", "lo_only", "sd_hi"]


def test_share_is_a_fraction_pair_never_a_bare_decimal():
    """Attempt 2: a bare decimal share can spell a retracted historical figure (Q6)."""
    assert _share(4127, 34428) == "4127/34428 (~1.1987e-1)"
    assert _share(0, 1653) == "0/1653 (~0.0000e0)"
    assert _share(1, 2) == "1/2 (~5.0000e-1)"
    assert _share(7, 0) == ""
