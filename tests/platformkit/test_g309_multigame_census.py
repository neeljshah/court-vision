"""G309 per-file test -- 3-game SYNTHETIC construct, n = 3 (CONSTRUCT).

Pins the four metrics the census exists to report -- coverage, id churn, ball share and the
zero-step liveness share -- plus the bbox-bottom-centre footpoint convention and the
nearest-rank p95, against hand-computed values. No pod, no real data.

Run ONLY this file:
  python -m pytest tests/platformkit/test_g309_multigame_census.py -q
"""

import csv
import json
import os

from scripts.platformkit.tracking import g309_multigame_census as m

TRACK_COLS = ["frame", "player_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
              "source_height", "coordinate_space"]
BALL_COLS = ["frame", "ball_x2d", "ball_y2d", "detected", "ball_inferred"]


def _write(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _p(frame, pid, x1, y2, x2):
    return {"frame": frame, "player_id": pid, "bbox_x1": x1, "bbox_y1": 0,
            "bbox_x2": x2, "bbox_y2": y2, "source_height": 100,
            "coordinate_space": "image_px"}


def _build(root):
    # gA: footpoints p1 (5,50)->(5,50)->(15,50) [steps 0, 10]; p2 (10,50)->(10,80) [step 30]
    _write(os.path.join(root, "gA", "tracking_data.csv"), TRACK_COLS, [
        _p(0, "1", 0, 50, 10), _p(0, "2", 0, 50, 20),
        _p(1, "1", 0, 50, 10), _p(1, "2", 0, 80, 20),
        _p(2, "1", 10, 50, 20),
    ])
    _write(os.path.join(root, "gA", "ball_tracking.csv"), BALL_COLS, [
        {"frame": 0, "ball_x2d": 1, "ball_y2d": 2, "detected": 1, "ball_inferred": 0},
        {"frame": 1, "ball_x2d": 3, "ball_y2d": 4, "detected": 0, "ball_inferred": 1},
        {"frame": 2, "ball_x2d": "", "ball_y2d": "", "detected": 0, "ball_inferred": 0},
    ])
    # gB: 4 one-row tracks in one frame; ball head produced nothing
    _write(os.path.join(root, "gB", "tracking_data.csv"), TRACK_COLS,
           [_p(0, str(i), 0, 50, 10) for i in range(1, 5)])
    _write(os.path.join(root, "gB", "ball_tracking.csv"), BALL_COLS, [
        {"frame": 0, "ball_x2d": "", "ball_y2d": "", "detected": 0, "ball_inferred": 0},
        {"frame": 1, "ball_x2d": "", "ball_y2d": "", "detected": 0, "ball_inferred": 0},
    ])
    # gC: 6 boxes in one frame, no ball file, NO ledger row (in flight)
    _write(os.path.join(root, "gC", "tracking_data.csv"), TRACK_COLS,
           [_p(0, str(i), 0, 50, 10) for i in range(1, 7)])
    led = [
        {"game_id": "gA", "rows": 5, "decoded_frames": 30, "stride": 3, "coverage_pct": 0.1,
         "passed": False, "status": "tracked", "rung": "IMAGE_PX_DECLARED", "sport": "test",
         "failure_heads": ["coordinate_contract: no court calibration sidecar"]},
        {"game_id": "gB", "rows": 4, "decoded_frames": 30, "stride": 3, "coverage_pct": 0.0333,
         "passed": False, "status": "tracked", "rung": "IMAGE_PX_DECLARED", "sport": "test",
         "failure_heads": []},
    ]
    with open(os.path.join(root, "track_daemon_ledger.jsonl"), "w", encoding="ascii") as fh:
        fh.write('{"game_id": "gA", "status": "thin", "passed": null, "rows": 0}\n')
        for d in led:
            fh.write(json.dumps(d) + "\n")


def test_census_three_game_construct(tmp_path):
    root = str(tmp_path / "data" / "tracking")
    os.makedirs(root)
    _build(root)
    rows, ledger, n_lines, n_passed = m.census(root)
    by = {r["game_id"]: r for r in rows}

    # ACCEPTANCE: one census row per game directory with a tracking_data.csv, no duplicates,
    # and every ledger game_id that has one appears exactly once.
    assert [r["game_id"] for r in rows] == ["gA", "gB", "gC"]
    for g in ledger:
        assert sum(1 for r in rows if r["game_id"] == g) == 1

    # PREMISE counting: the thin (passed=null) line is NOT adjudicated.
    assert (n_lines, n_passed) == (3, 2)

    a = by["gA"]
    assert (a["rows"], a["frames_emitted"], a["distinct_track_ids"]) == (5, 3, 2)
    assert a["median_track_len_rows"] == 2.5
    assert a["id_churn_per_detection"] == 2 / 5
    # frames_attempted = ceil(30 / 3) = 10; the two coverages differ BY THE STRIDE.
    assert (a["frames_attempted"], a["decoded_frames"]) == (10, 30)
    assert a["coverage_attempted_frames_pct"] == 3 / 10
    assert a["coverage_decoded_pct"] == 3 / 30
    assert a["rows_match_ledger"] is True and a["coverage_match_ledger_4dp"] is True
    # footpoint = bbox bottom-centre; steps 0.0, 10.0 (p1) and 30.0 (p2); p95 nearest-rank = 30
    assert a["n_steps"] == 3
    assert a["p95_disp_norm"] == 30.0 / 100.0
    assert a["zero_step_share"] == 1 / 3
    assert a["share_frames_ge6_boxes"] == 0.0
    assert (a["ball_rows"], a["ball_detected"], a["ball_inferred"], a["ball_none"]) == (3, 1, 1, 1)
    assert a["ball_valid_share"] == 2 / 3
    assert a["failure_head"].startswith("coordinate_contract")

    b = by["gB"]
    assert b["ball_rows"] == 2 and b["ball_detected"] == 0 and b["ball_valid_share"] == 0.0
    assert b["id_churn_per_detection"] == 1.0
    assert b["n_steps"] == 0 and b["p95_disp_norm"] is None and b["zero_step_share"] is None
    assert b["ledger_row"] == "present" and b["rows_match_ledger"] is True

    c = by["gC"]
    assert c["ledger_row"] == "absent" and c["ledger_rows"] is None
    assert c["share_frames_ge6_boxes"] == 1.0
    assert c["ball_rows"] == 0 and c["ball_valid_share"] is None
    assert c["frames_attempted"] is None and c["coverage_attempted_frames_pct"] is None
