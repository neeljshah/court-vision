"""G314 -- do `ball_inferred` rows carry a coordinate?  (premise re-measurement)

Counts, over EVERY row of a ball table, the four numbers the G314 spec fixes:
`ball_rows`, `ball_detected`, `ball_inferred`, and the number of `ball_inferred`
rows carrying a finite `ball_x2d` AND `ball_y2d`.  The last one is the premise:
the spec asserts it is 0.

Image space only (`coordinate_space = image_px`).  A coordinate is NOT a correct
coordinate: nothing here is recall, precision, accuracy or registration, and no
position counted here has ever been checked against an image.

The truth and finiteness predicates are IMPORTED from the G309 census reader so
they cannot drift from the numbers this row is checking.

G320 hardening (additive): `count_ball_table` STOPS on a table with no
`ball_inferred` header rather than reporting its flag counts as zero, and counts
`inferred_no_coord` -- flagged rows with no finite coordinate pair -- as its own
class, recording their frame ids.

    python -m scripts.platformkit.tracking.g314_ball_inferred_coords <scratch_dir>
"""
from __future__ import annotations

import csv
import os
import sys

from scripts.platformkit.tracking.g309_multigame_census import _f

# The G309 census truth set, quoted verbatim from g309_multigame_census.py:138-140.
TRUE_TOKENS = ("1", "1.0", "True", "true")

# A9: name the exact source.  Pod bytes asserted before any count is taken.
POD_DIR = "/workspace/nba-ai-system/data/tracking"
INPUTS = (
    ("wnba_05", "ball_tracking.csv", 24473),
    ("wnba_05", "tracking_data.csv", 1759850),
    ("wnba_02", "ball_tracking.csv", 23410),
    ("wnba_02", "tracking_data.csv", 2398304),
)


class MissingBallInferredHeader(RuntimeError):
    """G320: the table carries no `ball_inferred` header, so it cannot be classified.

    G314's verifier flagged that reporting 0 flagged rows for such a table is a
    silent miscount: absent evidence read as evidence of absence.  Stop instead.
    """


def _truth(cell) -> bool:
    return (cell or "").strip() in TRUE_TOKENS


def count_ball_table(path: str) -> dict:
    """Count the four spec numbers plus the detected x inferred cross-tab."""
    out = {
        "ball_rows": 0, "ball_detected": 0, "ball_inferred": 0, "ball_none": 0,
        "ball_valid": 0, "inferred_with_coords": 0, "inferred_without_coords": 0,
        "det_and_inf": 0, "det_not_inf": 0, "inf_not_det": 0, "neither": 0,
        "has_inferred_column": False,
        # G320 (additive, B2): the flagged-but-uncoordinated class, kept as its own
        # class instead of being folded into ball_detected or ball_inferred.  Equal
        # by construction to `inferred_without_coords`, which keeps its own name and
        # meaning unchanged; the G320 test asserts the two cannot drift apart.
        "inferred_no_coord": 0, "inferred_no_coord_frames": [],
    }
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        if "ball_inferred" not in (reader.fieldnames or []):
            raise MissingBallInferredHeader(
                "%s has no ball_inferred header; columns = %s"
                % (path, list(reader.fieldnames or [])))
        out["has_inferred_column"] = True
        for r in reader:
            out["ball_rows"] += 1
            det = _truth(r.get("detected"))
            inf = _truth(r.get("ball_inferred"))
            finite = (_f(r.get("ball_x2d")) is not None
                      and _f(r.get("ball_y2d")) is not None)
            out["ball_detected"] += int(det)
            out["ball_inferred"] += int(inf)
            out["ball_none"] += int(not det and not inf)
            out["ball_valid"] += int(finite)
            if inf:
                out["inferred_with_coords"] += int(finite)
                out["inferred_without_coords"] += int(not finite)
                if not finite:
                    out["inferred_no_coord"] += 1
                    out["inferred_no_coord_frames"].append(
                        (r.get("frame") or "").strip())
            out["det_and_inf"] += int(det and inf)
            out["det_not_inf"] += int(det and not inf)
            out["inf_not_det"] += int(inf and not det)
            out["neither"] += int(not det and not inf)
    n = out["ball_rows"]
    out["ball_valid_share"] = (out["ball_valid"] / n) if n else None
    out["detected_share"] = (out["ball_detected"] / n) if n else None
    out["share_identity_holds"] = (
        n > 0 and out["ball_valid_share"] == out["detected_share"]
    )
    return out


def count_tracking_data(path: str) -> dict:
    """`tracking_data.csv` carries ball coords but NO `ball_inferred` column."""
    rows = valid = 0
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        for r in reader:
            rows += 1
            if (_f(r.get("ball_x2d")) is not None
                    and _f(r.get("ball_y2d")) is not None):
                valid += 1
    return {
        "rows": rows,
        "ball_coord_rows": valid,
        "has_inferred_column": "ball_inferred" in cols,
        "n_cols": len(cols),
    }


def assert_bytes(scratch: str) -> list:
    """A9: every input's byte size must match the pod listing, or STOP."""
    seen = []
    for game, name, want in INPUTS:
        local = os.path.join(scratch, "%s_%s" % (game, name))
        got = os.path.getsize(local)
        if got != want:
            raise SystemExit(
                "STOP: %s/%s is %d bytes locally, pod listing says %d"
                % (game, name, got, want))
        seen.append((game, name, want, "%s/%s/%s" % (POD_DIR, game, name)))
    return seen


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: g314_ball_inferred_coords.py <scratch_dir>")
        return 2
    scratch = argv[0]
    print("G314 -- ball_inferred coordinate premise (image_px only; no eye check)")
    for game, name, size, pod in assert_bytes(scratch):
        print("INPUT %s  %d bytes  (byte-identical to the pod listing)" % (pod, size))
    print("")
    premise_counts = []
    for game in ("wnba_05", "wnba_02"):
        b = count_ball_table(os.path.join(scratch, "%s_ball_tracking.csv" % game))
        t = count_tracking_data(os.path.join(scratch, "%s_tracking_data.csv" % game))
        premise_counts.append(b["inferred_with_coords"])
        print("== %s ==" % game)
        print("  ball_tracking.csv (the file the G309 census read; has ball_inferred=%s)"
              % b["has_inferred_column"])
        print("    ball_rows            = %d" % b["ball_rows"])
        print("    ball_detected        = %d" % b["ball_detected"])
        print("    ball_inferred        = %d" % b["ball_inferred"])
        print("    inferred WITH finite ball_x2d AND ball_y2d = %d"
              % b["inferred_with_coords"])
        print("    inferred WITHOUT a finite pair             = %d"
              % b["inferred_without_coords"])
        print("    cross-tab det/inf: both=%d  det_only=%d  inf_only=%d  neither=%d"
              % (b["det_and_inf"], b["det_not_inf"], b["inf_not_det"], b["neither"]))
        print("    ball_valid_share=%s  detected/rows=%s  identity_holds=%s"
              % (b["ball_valid_share"], b["detected_share"], b["share_identity_holds"]))
        print("  tracking_data.csv (%d cols; has ball_inferred=%s)"
              % (t["n_cols"], t["has_inferred_column"]))
        print("    rows=%d  rows with a finite ball_x2d AND ball_y2d=%d"
              % (t["rows"], t["ball_coord_rows"]))
        print("")
    verdict = "PREMISE TRUE" if all(c == 0 for c in premise_counts) else "PREMISE FALSE"
    print("%s: inferred-with-coordinate counts = %s (spec asserts 0 on both)"
          % (verdict, premise_counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
