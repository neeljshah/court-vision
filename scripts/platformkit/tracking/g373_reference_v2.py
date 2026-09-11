"""G373 phase 1: reference v2 diagnostics, adjudication queue and census.

The v1 census is never edited.  reference_v2.csv is a SEPARATE census built from
the native blind ratings, and both are reported side by side.

The usability bar is fixed by the sealed phase-1 amendment and is not evaluated
anywhere else: over the both-VISIBLE pairs, median centre disagreement must be
<= 0.5 x median native diameter with at least 30 such pairs.  Median alone can
hide nearly half the bad localizations, so p90 and missingness over ALL scheduled
keys are reported beside it, each with its population named.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import read_csv, write_csv
from scripts.platformkit.tracking.g363_centre_diag import quantiles
from scripts.platformkit.tracking.g363_score import cohen_kappa

ADJUDICATOR = "ADJUDICATOR"
PRIMARY = ("sol", "terra")
NATIVE_FLOOR_PX = 4.5
MIN_PAIRS = 30
BAR_DIAMETER_MULTIPLE = 0.5
REFERENCE_FIELDS = ("frame_key", "split", "source", "label", "box_x", "box_y", "box_w",
                    "box_h", "cx", "cy", "diameter", "decided_by", "n_raters")


def latest(rows: list[dict]) -> dict | None:
    """One rating per rater: a crop_refine row supersedes that rater's full_frame row."""
    if not rows:
        return None
    refined = [row for row in rows if row.get("pass") == "crop_refine"]
    return (refined or rows)[-1]


def by_frame(ratings: list[dict]) -> dict[str, dict[str, dict]]:
    """frame_key -> rater -> that rater's surviving rating."""
    buckets: dict[str, dict[str, list[dict]]] = {}
    for row in ratings:
        buckets.setdefault(row["frame_key"], {}).setdefault(row["rater"], []).append(row)
    return {key: {rater: latest(rows) for rater, rows in raters.items()}
            for key, raters in buckets.items()}


def centre(row: dict) -> tuple[float, float] | None:
    try:
        return float(row["cx"]), float(row["cy"])
    except (TypeError, ValueError):
        return None


def diameter(row: dict) -> float | None:
    try:
        return max(float(row["box_w"]), float(row["box_h"]))
    except (TypeError, ValueError):
        return None


def pair_diagnostics(scheduled: list[str], frames: dict[str, dict[str, dict]]) -> dict:
    """Agreement and missingness over ALL scheduled keys, populations named."""
    gaps: list[float] = []
    diameters: list[float] = []
    labels_a: list[str] = []
    labels_b: list[str] = []
    counts = {"scheduled": len(scheduled), "rated_by_both": 0, "rated_by_one": 0,
              "rated_by_none": 0, "both_visible": 0, "label_disagreement": 0,
              "both_visible_missing_box": 0}
    for key in scheduled:
        raters = frames.get(key, {})
        present = [raters.get(name) for name in PRIMARY]
        if all(present):
            counts["rated_by_both"] += 1
            labels_a.append(present[0]["label"])
            labels_b.append(present[1]["label"])
            if present[0]["label"] != present[1]["label"]:
                counts["label_disagreement"] += 1
                continue
            if present[0]["label"] != "VISIBLE":
                continue
            counts["both_visible"] += 1
            centres = [centre(row) for row in present]
            sizes = [diameter(row) for row in present]
            if None in centres or None in sizes:
                counts["both_visible_missing_box"] += 1
                continue
            gaps.append(math.hypot(centres[0][0] - centres[1][0], centres[0][1] - centres[1][1]))
            diameters.extend(sizes)
        elif any(present):
            counts["rated_by_one"] += 1
        else:
            counts["rated_by_none"] += 1
    gap_stats = quantiles(gaps)
    diameter_stats = quantiles(diameters)
    bar = (BAR_DIAMETER_MULTIPLE * diameter_stats["p50"]) if diameter_stats.get("n") else None
    usable = bool(bar is not None and gap_stats.get("n", 0) >= MIN_PAIRS
                  and gap_stats["p50"] <= bar)
    return {
        "counts": counts,
        "centre_disagreement_native_px": {
            "population": "both-VISIBLE pairs carrying a box from each primary rater",
            **gap_stats},
        "native_diameter_px": {
            "population": "every box of a both-VISIBLE pair, one per rater per frame",
            **diameter_stats},
        "cohen_kappa": cohen_kappa(labels_a, labels_b),
        "bar": {"rule": "median centre disagreement <= 0.5 x median native diameter",
                "min_pairs": MIN_PAIRS, "threshold_px": bar,
                "observed_median_px": gap_stats.get("p50"),
                "observed_pairs": gap_stats.get("n", 0),
                "verdict": "usable" if usable else "LIMIT"},
    }


def adjudication_queue(scheduled: list[str], frames: dict[str, dict[str, dict]]) -> list[dict]:
    """Frames the two primaries did not settle: differing labels, or both VISIBLE
    with centres further apart than the native matching tolerance for that frame."""
    queue: list[dict] = []
    for key in scheduled:
        raters = frames.get(key, {})
        if raters.get(ADJUDICATOR):
            continue
        present = [raters.get(name) for name in PRIMARY]
        if not all(present):
            queue.append({"frame_key": key, "why": "MISSING-RATING"})
            continue
        if present[0]["label"] != present[1]["label"]:
            queue.append({"frame_key": key, "why": "LABEL-DISAGREEMENT"})
            continue
        if present[0]["label"] != "VISIBLE":
            continue
        centres = [centre(row) for row in present]
        sizes = [diameter(row) for row in present]
        if None in centres or None in sizes:
            queue.append({"frame_key": key, "why": "MISSING-BOX"})
            continue
        gap = math.hypot(centres[0][0] - centres[1][0], centres[0][1] - centres[1][1])
        if gap > max(NATIVE_FLOOR_PX, sum(sizes) / len(sizes) / 2.0):
            queue.append({"frame_key": key, "why": "CENTRE-GAP",
                          "gap_native_px": round(gap, 2)})
    return queue


def wide_pair(present: list[dict]) -> bool:
    """True when two VISIBLE raters are further apart than the native tolerance.

    The sealed amendment sends exactly these frames to adjudication, so the census
    must NOT quietly average them: two centres 200 px apart average to a box on
    nothing, which as a training label is worse than no label at all."""
    centres = [centre(row) for row in present]
    sizes = [diameter(row) for row in present]
    if None in centres or None in sizes:
        return True
    gap = math.hypot(centres[0][0] - centres[1][0], centres[0][1] - centres[1][1])
    return gap > max(NATIVE_FLOOR_PX, sum(sizes) / len(sizes) / 2.0)


def census(scheduled: list[dict], frames: dict[str, dict[str, dict]]) -> tuple[list[dict], dict]:
    """The v2 reference: the adjudicated row where one exists, the agreed row
    otherwise.  An unsettled frame is reported as missingness, never dropped."""
    rows: list[dict] = []
    unsettled = 0
    unsettled_wide = 0
    for entry in scheduled:
        key = entry["frame_key"]
        raters = frames.get(key, {})
        judged = raters.get(ADJUDICATOR)
        present = [raters.get(name) for name in PRIMARY]
        chosen, decided = None, ""
        if judged:
            chosen, decided = judged, ADJUDICATOR
        elif all(present) and present[0]["label"] == present[1]["label"]:
            chosen, decided = present[0], "AGREED"
        if chosen is None:
            unsettled += 1
            continue
        if chosen["label"] == "VISIBLE" and decided == "AGREED":
            centres = [centre(row) for row in present]
            sizes = [diameter(row) for row in present]
            if None in centres or None in sizes or wide_pair(present):
                unsettled += 1
                unsettled_wide += 1
                continue
            cx = sum(item[0] for item in centres) / len(centres)
            cy = sum(item[1] for item in centres) / len(centres)
            size = sum(sizes) / len(sizes)
            box = {"box_x": "", "box_y": "", "box_w": "", "box_h": ""}
        elif chosen["label"] == "VISIBLE":
            cx, cy = centre(chosen)
            size = diameter(chosen)
            box = {key_: chosen[key_] for key_ in ("box_x", "box_y", "box_w", "box_h")}
        else:
            cx = cy = size = ""
            box = {"box_x": "", "box_y": "", "box_w": "", "box_h": ""}
        rows.append({"frame_key": key, "split": entry["split"], "source": entry["source"],
                     "label": chosen["label"], "cx": cx, "cy": cy, "diameter": size,
                     "decided_by": decided, "n_raters": sum(1 for row in present if row),
                     **box})
    return rows, {"unsettled_frames": unsettled, "census_rows": len(rows),
                  "unsettled_wide_or_boxless_pair": unsettled_wide}


def run(args) -> int:
    scheduled = [{"frame_key": row["frame_key"], "split": row["split"],
                  "source": row.get("source", "")}
                 for row in read_csv(Path(args.manifest))]
    ratings = read_csv(Path(args.ratings))
    frames = by_frame(ratings)
    keys = [row["frame_key"] for row in scheduled]
    diagnostics = pair_diagnostics(keys, frames)
    queue = adjudication_queue(keys, frames)
    rows, summary = census(scheduled, frames)
    write_csv(Path(args.out), REFERENCE_FIELDS, rows)
    write_csv(Path(args.queue), ("frame_key", "why", "gap_native_px"), queue)
    payload = {**diagnostics, "census": summary,
               "adjudication_queue": len(queue),
               "queue_reasons": {why: sum(1 for row in queue if row["why"] == why)
                                 for why in sorted({row["why"] for row in queue})}}
    Path(args.summary).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                                  encoding="ascii", newline="\n")
    print("REFERENCE-V2 " + json.dumps({"bar": payload["bar"], "counts": payload["counts"],
                                        "queue": payload["adjudication_queue"]}, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g373_reference_v2")
    for flag in ("--manifest", "--ratings", "--out", "--queue", "--summary"):
        parser.add_argument(flag, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
