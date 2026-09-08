"""G320 CONSTRUCT: the hardened G314 reader stops on a missing flag header, and
counts the flagged-but-uncoordinated rows as their own class.

Two behaviours are pinned, both pre-registered in `g320_prereg_2026-09-08.md`:
  1. a ball table whose header omits `ball_inferred` makes `count_ball_table`
     RAISE, instead of reporting its flag counts as zero (absent evidence must
     not be read as evidence of absence);
  2. a table carrying the shape found on the pod -- rows flagged inferred, not
     detected, with no coordinate -- reports `inferred_no_coord = 7` over its
     stated n, and that class does not drift from `inferred_without_coords`.
A third case pins the census SCOPE PREDICATE.

Image space only.  No frame is decoded and no coordinate here is claimed correct.
"""
from __future__ import annotations

import csv

import pytest

from scripts.platformkit.tracking.g314_ball_inferred_coords import (
    MissingBallInferredHeader, count_ball_table,
)
from scripts.platformkit.tracking.g320_ball_table_census import is_ball_table

FIELDS = ["frame", "timestamp", "ball_x2d", "ball_y2d", "detected", "live", "ball_inferred"]

# n = 20 rows (CONSTRUCT).  Exactly 7 carry the pod shape: detected=0, inferred=1,
# no finite coordinate -- spread over every non-finite spelling `float()` accepts
# or rejects.  The other 13 are contrast rows that must NOT enter the class.
NO_COORD_7 = [
    (444, "", ""), (540, "", ""), (750, "nan", "nan"), (1746, "inf", "435"),
    (2064, "435", "-inf"), (2100, "435", ""), (2823, "", "449"),
]
CONTRAST_13 = [
    (438, 1, 1, "464", "446"), (441, 1, 0, "29", "352"), (447, 1, 0, "132", "130"),
    (534, 1, 1, "9", "411"), (537, 1, 0, "91", "449"), (543, 1, 0, "91", "449"),
    (744, 1, 1, "68", "450"), (753, 1, 0, "784", "419"), (1743, 1, 0, "153", "314"),
    (2061, 1, 0, "111", "155"), (2067, 0, 0, "", ""), (2070, 0, 0, "", ""),
    (2826, 1, 0, "367", "440"),
]


def _write(path, rows, fields=FIELDS):
    with open(str(path), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: v for k, v in r.items() if k in fields})


def _row(frame, det, inf, x, y):
    return {"frame": frame, "timestamp": round(frame / 30.0, 3), "ball_x2d": x,
            "ball_y2d": y, "detected": det, "live": 1, "ball_inferred": inf}


def test_missing_ball_inferred_header_raises(tmp_path):
    """A table with the coordinate columns but no flag header must STOP the reader."""
    path = tmp_path / "no_flag_header.csv"
    fields = [f for f in FIELDS if f != "ball_inferred"]
    _write(path, [_row(1, 1, 0, "10", "20"), _row(2, 0, 0, "", "")], fields)

    assert is_ball_table(fields) is True, "still a ball table: it has both coord columns"
    with pytest.raises(MissingBallInferredHeader) as excinfo:
        count_ball_table(str(path))
    assert "ball_inferred" in str(excinfo.value)


def test_seven_flagged_rows_without_a_coordinate(tmp_path):
    """n = 20 rows (CONSTRUCT); exactly 7 are flagged inferred with no coordinate."""
    rows = [_row(f, 0, 1, x, y) for f, x, y in NO_COORD_7]
    rows += [_row(f, d, i, x, y) for f, d, i, x, y in CONTRAST_13]
    rows.sort(key=lambda r: r["frame"])
    path = tmp_path / "ball_tracking.csv"
    _write(path, rows)

    got = count_ball_table(str(path))
    assert got["ball_rows"] == len(rows) == 20          # the n this count is over
    assert got["inferred_no_coord"] == 7
    assert sorted(int(f) for f in got["inferred_no_coord_frames"]) == \
        sorted(f for f, _, _ in NO_COORD_7)

    # B2: the new class must not drift from the field G314 already published.
    assert got["inferred_no_coord"] == got["inferred_without_coords"]

    # The class is its OWN class: it is folded into neither of the two totals a
    # census reports, which is exactly why a census reading only those two
    # miscounts these rows.
    assert got["ball_detected"] == 11
    assert got["ball_inferred"] == 10
    assert got["inferred_with_coords"] == 3
    assert got["inferred_no_coord"] + got["inferred_with_coords"] == got["ball_inferred"]
    assert got["inf_not_det"] == 7        # every one of the 7 is undetected


def test_census_scope_predicate():
    """A ball table is one carrying BOTH per-row ball coordinate columns."""
    assert is_ball_table(FIELDS) is True
    assert is_ball_table(["frame", "ball_x2d", "detected"]) is False
    assert is_ball_table(["frame", "ball_y2d", "ball_inferred"]) is False
    assert is_ball_table(["game_id", "ball_rows", "ball_detected", "ball_inferred"]) is False
    assert is_ball_table([]) is False
