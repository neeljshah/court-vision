"""G315 -- SYNTHETIC CONSTRUCT pinning the step, gap and candidate arithmetic.

n = 1 (CONSTRUCT): every case below is enumerated by hand, not sampled, so the Q7
sampling rail does not bind. Nothing here touches the pod, `src/` or any real table.
"""

import csv
import math

from scripts.platformkit.tracking.g315_same_id_step_screen import (
    CANDIDATE_THRESHOLD, gap_bin, nearest_rank, modal_stride, pick_examples, screen_game,
)

HEIGHT = 100.0
HEADER = ["frame", "player_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
          "source_height"]


def _write(tmp_path, rows):
    d = tmp_path / "gsynth"
    d.mkdir()
    p = d / "tracking_data.csv"
    with open(p, "w", encoding="ascii", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        for r in rows:
            w.writerow(r)
    return str(p)


def test_nearest_rank_is_ceil_minus_one():
    v = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    assert nearest_rank(v, 0.95) == 1.0        # ceil(9.5)-1 = 9 -> 1.0
    assert nearest_rank(v, 0.50) == 0.5        # ceil(5.0)-1 = 4 -> 0.5
    assert nearest_rank(v, 0.75) == 0.8        # ceil(7.5)-1 = 7 -> 0.8
    assert nearest_rank([], 0.95) is None


def test_modal_stride_and_gap_bins():
    assert modal_stride([0, 3, 6, 9, 30]) == 3          # 3,3,3,21 -> 3
    assert modal_stride([5]) is None
    assert gap_bin(3, 3) == "B1_one_stride"
    assert gap_bin(6, 3) == "B2_le5x"
    assert gap_bin(15, 3) == "B2_le5x"                  # exactly 5x is still B2
    assert gap_bin(18, 3) == "B3_gt5x"
    assert gap_bin(3, None) == "B_unknown_stride"


def test_pick_examples_is_decile_midpoints_not_a_top_slice():
    cands = [{"step_norm": i / 100.0} for i in range(1, 101)]   # ranks 1..100
    picked = pick_examples(cands, k=10)
    assert [r for r, _ in picked] == [5, 15, 25, 35, 45, 55, 65, 75, 85, 95]
    assert min(c["step_norm"] for _, c in picked) == 0.05       # NOT a tail slice
    assert len(pick_examples(cands[:4], k=10)) == 4             # n < k -> take all


def test_step_gap_and_candidate_arithmetic_against_hand_values(tmp_path):
    # Track "a": footpoint (10,10) -> (40,50): hypot(30,40) = 50 px / 100 = 0.50, gap 3.
    # Then (40,50) -> (45,50): 5 px = 0.05, gap 3.  Then a 30-frame jump of 80 px = 0.80.
    # Track "b": one 20 px step = 0.20 over gap 6.  Track "c": a single unpaired row.
    # One row has a non-finite bbox and must be DROPPED, not paired across.
    rows = [
        [0, "a", 0, 0, 20, 10, HEIGHT],      # footpoint (10, 10)
        [3, "a", 30, 0, 50, 50, HEIGHT],     # footpoint (40, 50)  -> 0.50 cand, gap 3
        [6, "a", 35, 0, 55, 50, HEIGHT],     # footpoint (45, 50)  -> 0.05, gap 3
        [36, "a", 120, 0, 130, 50, HEIGHT],  # footpoint (125, 50) -> 0.80 cand, gap 30
        [0, "b", 0, 0, 10, 10, HEIGHT],      # footpoint (5, 10)
        [6, "b", 0, 0, 10, 30, HEIGHT],      # footpoint (5, 30)   -> 0.20, gap 6
        [9, "c", 0, 0, 10, 10, HEIGHT],
        [12, "c", "nan", 0, 10, 10, HEIGHT],  # dropped -> "c" stays unpaired
    ]
    dist, ex = screen_game("gsynth", _write(tmp_path, rows))

    assert dist["rows"] == 8 and dist["dropped_rows"] == 1
    assert dist["distinct_track_ids"] == 3 and dist["n_steps"] == 4
    assert dist["stride"] == 3 and dist["source_height"] == HEIGHT

    steps = sorted([0.50, 0.05, 0.80, 0.20])
    assert math.isclose(dist["p50_nr"], steps[math.ceil(0.50 * 4) - 1])   # 0.20
    assert math.isclose(dist["p75_nr"], steps[math.ceil(0.75 * 4) - 1])   # 0.50
    assert math.isclose(dist["p95_nr"], steps[math.ceil(0.95 * 4) - 1])   # 0.80
    assert math.isclose(dist["max_step"], 0.80)

    # Candidates are strictly above 0.30: {0.50 @ gap 3, 0.80 @ gap 30}.
    assert CANDIDATE_THRESHOLD == 0.30
    assert dist["n_candidates"] == 2
    assert math.isclose(dist["share_gt_0p30"], 0.5)
    assert math.isclose(dist["cand_share_of_steps"], 0.5)
    # The gap split is the whole point: one stride vs a 10-stride jump, never pooled.
    assert (dist["cand_b1_one_stride"], dist["cand_b2_le5x"], dist["cand_b3_gt5x"]) == (1, 0, 1)

    assert dist["n_examples"] == 2 and len(ex) == 2
    by_step = {round(e["step_norm"], 2): e for e in ex}
    assert by_step[0.50]["gap"] == 3 and by_step[0.50]["gap_bin"] == "B1_one_stride"
    assert by_step[0.80]["gap"] == 30 and by_step[0.80]["gap_bin"] == "B3_gt5x"
    assert by_step[0.50]["frame_a"] == 0 and by_step[0.50]["frame_b"] == 3
    assert by_step[0.80]["player_id"] == "a" and by_step[0.80]["cand_rank"] == 2
    assert by_step[0.50]["panel_id"] == "gsynth_01"
