"""G363 diagnostic: how far the arms land from the reference centre, and how far
the two blind raters land from each other, in the same normalised 720p pixels the
sealed matching rule uses.

This changes no bar and no metric.  It exists because a true positive requires the
prediction centre to fall inside max(3 px, reference_diameter_720p / 2), and the
reference centre itself carries rater disagreement: if that disagreement is wider
than the matching tolerance, a zero true-positive count is partly a property of
the reference, not only of the detector.  Both distributions are printed so a
reader can see which.  Output is a table, never a verdict.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import read_csv
from scripts.platformkit.tracking.g363_score import DEFAULT_REF_DIAMETER_720P, TARGET_HEIGHT, reference


def quantiles(values: list[float]) -> dict[str, float | int]:
    """Count plus the p50 / p90 / max of one distance series."""
    ordered = sorted(values)
    if not ordered:
        return {"n": 0}
    def pick(share: float) -> float:
        return round(ordered[min(len(ordered) - 1, int(share * len(ordered)))], 2)
    return {"n": len(ordered), "p50": pick(0.5), "p90": pick(0.9),
            "max": round(ordered[-1], 2)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="g363_centre_diag")
    parser.add_argument("--frames", required=True)
    parser.add_argument("--ratings", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--split", default="heldout")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    ratings = read_csv(Path(args.ratings))
    refs, _diagnostics = reference(ratings)
    by_frame: dict[str, list[dict]] = {}
    for row in ratings:
        by_frame.setdefault(row["frame_key"], []).append(row)
    preds: dict[str, dict[str, list[dict]]] = {}
    for row in read_csv(Path(args.predictions)):
        if row["rank"] == "0" and row["tick_history"] == "OBSERVED":
            preds.setdefault(row["arm"], {}).setdefault(row["frame_key"], []).append(row)

    rater_gap: list[float] = []
    nearest: dict[str, list[float]] = {}
    tolerance: list[float] = []
    for frame in read_csv(Path(args.frames)):
        key = frame["frame_key"]
        ref = refs.get(key)
        if frame["split"] != args.split or not ref or ref["label"] != "VISIBLE" or ref["cx"] is None:
            continue
        sheet_scale, scale = float(frame["sheet_scale"]), TARGET_HEIGHT / float(frame["height"])
        diameter = (ref["diameter"] / sheet_scale if ref["diameter"]
                    else DEFAULT_REF_DIAMETER_720P / scale)
        tolerance.append(max(3.0, diameter * scale / 2.0))
        centre = (ref["cx"] / sheet_scale, ref["cy"] / sheet_scale)
        primaries = [row for row in by_frame.get(key, [])
                     if row["rater"] != "ADJUDICATOR" and row.get("cx")]
        if len(primaries) == 2:
            rater_gap.append(math.hypot(float(primaries[0]["cx"]) - float(primaries[1]["cx"]),
                                        float(primaries[0]["cy"]) - float(primaries[1]["cy"]))
                             / sheet_scale * scale)
        for arm, frames in preds.items():
            found = frames.get(key, [])
            if found:
                nearest.setdefault(arm, []).append(
                    min(math.hypot(float(row["x"]) - centre[0], float(row["y"]) - centre[1]) * scale
                        for row in found))
    payload = {"split": args.split, "units": "pixels normalised to 720p",
               "matching_tolerance": quantiles(tolerance),
               "primary_rater_centre_gap": quantiles(rater_gap),
               "nearest_prediction_to_reference": {arm: quantiles(values)
                                                   for arm, values in sorted(nearest.items())}}
    Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                              encoding="utf-8", newline="\n")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
