"""G314 CONSTRUCT (n = 1): the detected x inferred x coordinate space, exhaustively.

The G314 spec expected `ball_inferred` rows to carry NO coordinate.  This construct
enumerates EVERY combination a ball row can take -- detected in {0,1} x inferred in
{0,1} x coordinate pair in {finite, empty} = 8 cases, plus the two non-finite spellings
(NaN, inf) that `float()` accepts and the reader must still reject -- and pins how the
counter classifies each.  Enumeration is exhaustive over the classifier's whole input
space, so Q7's n >= 30 sampling rail does not bind (Q7: `n = <k> (CONSTRUCT)`).

Image space only.  No frame is decoded and no coordinate here is claimed to be correct.
"""
from __future__ import annotations

import csv

from scripts.platformkit.tracking.g314_ball_inferred_coords import count_ball_table

FIELDS = ["frame", "timestamp", "ball_x2d", "ball_y2d", "detected", "live", "ball_inferred"]

# (detected, ball_inferred, ball_x2d, ball_y2d) -- all 8 flag/coordinate combinations,
# then the three cells `float()` parses but `math.isfinite` rejects, and a half-pair.
CASES = [
    (1, 0, "433", "446"), (1, 0, "", ""),
    (1, 1, "917", "435"), (1, 1, "", ""),
    (0, 0, "12", "13"), (0, 0, "", ""),
    (0, 1, "659", "445"), (0, 1, "", ""),
    (1, 1, "nan", "435"), (1, 1, "inf", "435"), (1, 1, "435", "-inf"),
    (1, 1, "435", ""),
]


def _write(path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for i, (det, inf, x, y) in enumerate(CASES):
            w.writerow({"frame": i, "timestamp": i / 30.0, "ball_x2d": x,
                        "ball_y2d": y, "detected": det, "live": 1,
                        "ball_inferred": inf})


def test_construct_enumerates_every_flag_and_coordinate_combination(tmp_path):
    path = tmp_path / "ball_tracking.csv"
    _write(path)
    got = count_ball_table(str(path))

    assert got["ball_rows"] == len(CASES) == 12
    assert got["has_inferred_column"] is True
    assert got["ball_detected"] == sum(d for d, _, _, _ in CASES) == 8
    assert got["ball_inferred"] == sum(i for _, i, _, _ in CASES) == 8

    # The premise number: an inferred row WITH a finite pair is counted as such.  The
    # four non-finite spellings (empty, nan, inf, -inf) and the half-pair are not.
    assert got["inferred_with_coords"] == 2
    assert got["inferred_without_coords"] == 6
    assert got["inferred_with_coords"] + got["inferred_without_coords"] == got["ball_inferred"]

    # detected and inferred are NOT a partition: they overlap, which is why
    # ball_detected + ball_inferred + ball_none can exceed ball_rows.
    assert got["det_and_inf"] == 6
    assert got["det_not_inf"] == 2
    assert got["inf_not_det"] == 2
    assert got["neither"] == 2
    assert got["ball_none"] == got["neither"] == 2
    assert got["ball_detected"] + got["ball_inferred"] + got["ball_none"] > got["ball_rows"]

    # The identity G309 read as "inferred rows carry no coordinate" is an identity
    # about the WRITER, not about inference: it holds only when every coordinate-
    # carrying row is a detected row.  This fixture breaks that and the identity fails.
    assert got["ball_valid"] == 4
    assert got["share_identity_holds"] is False


def test_identity_holds_when_coordinates_track_detected(tmp_path):
    """The pod shape: coordinates are written iff detected, inferred overlaps detected."""
    path = tmp_path / "ball_tracking.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for i, (det, inf) in enumerate([(1, 1), (1, 0), (0, 0), (1, 1)]):
            w.writerow({"frame": i, "timestamp": 0.0,
                        "ball_x2d": "10" if det else "", "ball_y2d": "20" if det else "",
                        "detected": det, "live": 1, "ball_inferred": inf})
    got = count_ball_table(str(path))
    assert got["ball_valid_share"] == got["detected_share"] == 0.75
    assert got["share_identity_holds"] is True
    assert got["inferred_with_coords"] == 2  # inferred rows DO carry a coordinate
