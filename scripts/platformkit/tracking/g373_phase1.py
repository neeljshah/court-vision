"""G373 phase 1: decode-cache identity and the binding A0/A7 premise replay.

Sealed by the G373 execution prereg and its phase-1 amendment.  Nothing here
edits a G363 artifact: frames.csv, ratings.csv, predictions.csv and
cache_manifest.csv are opened read-only, and the shared cache under
/workspace/wt/a7/data/g363_cache is never written.  The matcher, the reference
builder and the arm runner are IMPORTED from the G363 modules, never copied, so
the replay uses the same rule the archived counts were produced with.
"""
from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "OPENCV_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse
import json
import math
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import file_sha256, frame_key, read_csv
from scripts.platformkit.tracking.g363_centre_diag import quantiles
from scripts.platformkit.tracking.g363_score import (DEFAULT_REF_DIAMETER_720P, TARGET_HEIGHT,
                                                     reference, score_arm)

# The NEW screening gate of this successor row.  G363's own gate was 0.50 and its
# verdict is final; crossing this one does not resume that row.
NEW_A0_GATE = 0.05
IDENTITY_FIELDS = ("frame_key", "png_sha256_status", "decoded_key_status")


def verify_cache(cache: Path, manifest_rows: list[dict], progress: int = 250) -> dict:
    """Re-hash every cached PNG twice: file bytes against the sealed manifest, and
    decoded bytes against the frame key the sealed table names."""
    import cv2

    cv2.setNumThreads(1)
    rows: list[dict] = []
    counts = {"n": 0, "png_ok": 0, "png_mismatch": 0, "png_absent": 0,
              "decoded_ok": 0, "decoded_mismatch": 0, "decoded_unreadable": 0}
    for index, row in enumerate(manifest_rows):
        key = row["frame_key"]
        path = Path(cache) / row["png_file"]
        counts["n"] += 1
        if not path.exists():
            counts["png_absent"] += 1
            rows.append({"frame_key": key, "png_sha256_status": "ABSENT",
                         "decoded_key_status": "ABSENT"})
            continue
        png_ok = file_sha256(path) == row["png_sha256"]
        counts["png_ok" if png_ok else "png_mismatch"] += 1
        image = cv2.imread(str(path))
        if image is None:
            counts["decoded_unreadable"] += 1
            decoded_status = "UNREADABLE"
        else:
            decoded_ok = frame_key(image) == key
            counts["decoded_ok" if decoded_ok else "decoded_mismatch"] += 1
            decoded_status = "REPRODUCED" if decoded_ok else "UNKNOWN-ALIGNMENT"
        rows.append({"frame_key": key,
                     "png_sha256_status": "MATCH" if png_ok else "MISMATCH",
                     "decoded_key_status": decoded_status})
        if progress and counts["n"] % progress == 0:
            print(f"CACHE {counts['n']}/{len(manifest_rows)} png_ok={counts['png_ok']} "
                  f"decoded_ok={counts['decoded_ok']}", flush=True)
    counts["png_bytes_total"] = sum(int(row["png_bytes"]) for row in manifest_rows)
    return {"counts": counts, "rows": rows}


def nearest_centre_720p(frames: list[dict], refs: dict[str, dict], preds: list[dict],
                        arm: str) -> dict:
    """Distance at 720p from each VISIBLE reference centre to the nearest rank-0
    observed prediction on that same frame.  Named population, never a median alone."""
    by_frame: dict[str, list[dict]] = {}
    for row in preds:
        if row["arm"] == arm and row["rank"] == "0" and row["tick_history"] == "OBSERVED":
            by_frame.setdefault(row["frame_key"], []).append(row)
    distances: list[float] = []
    visible = 0
    for frame in frames:
        key = frame["frame_key"]
        ref = refs.get(key)
        if ref is None or ref["label"] != "VISIBLE" or ref["cx"] is None:
            continue
        visible += 1
        found = by_frame.get(key, [])
        if not found:
            continue
        scale = TARGET_HEIGHT / float(frame["height"])
        sheet_scale = float(frame["sheet_scale"])
        rx, ry = ref["cx"] / sheet_scale, ref["cy"] / sheet_scale
        distances.append(min(math.hypot(float(row["x"]) - rx, float(row["y"]) - ry) * scale
                             for row in found))
    return {"arm": arm, "population": "VISIBLE reference frames carrying a rank-0 prediction",
            "n_visible": visible, "estimator": "G363 g363_centre_diag.quantiles order statistic",
            **quantiles(distances)}


def tolerance_720p(frames: list[dict], refs: dict[str, dict], split: str) -> dict:
    """The sealed matching tolerance distribution over VISIBLE frames of one split."""
    values: list[float] = []
    for frame in frames:
        ref = refs.get(frame["frame_key"])
        if frame["split"] != split or ref is None or ref["label"] != "VISIBLE":
            continue
        scale = TARGET_HEIGHT / float(frame["height"])
        sheet_scale = float(frame["sheet_scale"])
        diameter = (ref["diameter"] / sheet_scale if ref["diameter"]
                    else DEFAULT_REF_DIAMETER_720P / scale)
        values.append(max(3.0, diameter * scale / 2.0))
    return {"population": f"VISIBLE {split} reference frames",
            "units": "pixels normalised to 720p", **quantiles(values)}


def rows_identical(archived: list[dict], fresh: list[dict]) -> dict:
    """Repeatability of the A0 route (contract B11): the two runs are compared row
    by row on geometry and score VALUE, so the archived file's signed fixed-width
    number formatting is not mistaken for a different prediction."""
    def keyed(rows, from_archive):
        out = {}
        for row in rows:
            if from_archive and (row["arm"] != "A0" or row["split"] != "heldout"):
                continue
            out[(row["frame_key"], row["rank"])] = (
                row["x"], row["y"], row["w"], row["h"], float(row["score"]),
                row["tick_history"], row["source"])
        return out

    left, right = keyed(archived, True), keyed(fresh, False)
    differing = [key for key in set(left) | set(right) if left.get(key) != right.get(key)]
    return {"archived_rows": len(left), "fresh_rows": len(right),
            "keys_identical": set(left) == set(right),
            "differing_rows": len(differing),
            "rows_identical": not differing}


def replay(evidence: Path, frames_csv: Path, ratings_csv: Path, archived_preds: Path,
           fresh_preds: Path, route_hashes: dict) -> dict:
    """Score the fresh A0 run and re-score the archived A7 run on the sealed v1
    reference, and read the NEW screening gate against the fresh A0 coverage."""
    frames = read_csv(frames_csv)
    refs, agreement = reference(read_csv(ratings_csv))
    archived = read_csv(archived_preds)
    fresh = read_csv(fresh_preds)
    heldout = [row for row in frames if row["split"] == "heldout"]

    a0_fresh, _ = score_arm("A0", "heldout", frames, refs, fresh)
    a0_archived, _ = score_arm("A0", "heldout", frames, refs, archived)
    a7_archived, _ = score_arm("A7", "heldout", frames, refs, archived)

    coverage = a0_fresh["coverage"]
    out = {
        "gate": {"name": "NEW A0 screening gate of G373",
                 "rule": "C0 >= 0.05 is PREMISE FALSE",
                 "value": NEW_A0_GATE,
                 "note": "NEW; distinct from G363's own 0.50 gate. Crossing it does not "
                         "resume the historical x3 row, whose verdict is LIMIT and final.",
                 "c0_fresh": coverage,
                 "premise_false": bool(coverage >= NEW_A0_GATE)},
        "route_hashes_A11": route_hashes,
        "reference": {"census": "G363 v1 adjudicated (sealed, unedited)", **agreement},
        "counts": {
            "A0_fresh_heldout": {key: a0_fresh[key] for key in
                                 ("n_frames", "n_visible", "n_absent", "n_unknown", "tp", "fp",
                                  "coverage", "precision_wilson_lo", "fp_per_absent")},
            "A0_archived_heldout": {"tp": a0_archived["tp"], "fp": a0_archived["fp"],
                                    "n_frames": a0_archived["n_frames"]},
            "A0_historical_memo": {"tp": 0, "fp": 8},
            "A7_archived_heldout": {"tp": a7_archived["tp"], "fp": a7_archived["fp"],
                                    "n_frames": a7_archived["n_frames"]},
            "A7_historical_memo": {"tp": 2, "fp": 178},
        },
        "reproduces_archived": {
            "A0": a0_archived["tp"] == 0 and a0_archived["fp"] == 8,
            "A7": a7_archived["tp"] == 2 and a7_archived["fp"] == 178,
        },
        "fresh_vs_archived_A0": {
            "counts_identical": (a0_fresh["tp"] == a0_archived["tp"]
                                 and a0_fresh["fp"] == a0_archived["fp"]),
            **rows_identical(archived, fresh),
        },
        "nearest_centre": {
            "A0_fresh": nearest_centre_720p(heldout, refs, fresh, "A0"),
            "A0_archived": nearest_centre_720p(heldout, refs, archived, "A0"),
            "A7_archived": nearest_centre_720p(heldout, refs, archived, "A7"),
        },
        "matching_tolerance": tolerance_720p(frames, refs, "heldout"),
    }
    (Path(evidence) / "binding_replay.json").write_text(
        json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    return out


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g373_phase1")
    sub = parser.add_subparsers(dest="cmd", required=True)
    cache = sub.add_parser("cache-identity")
    cache.add_argument("--manifest", required=True)
    cache.add_argument("--cache", required=True)
    cache.add_argument("--out", required=True)
    rep = sub.add_parser("replay")
    for flag in ("--evidence", "--frames", "--ratings", "--archived-predictions",
                 "--fresh-predictions", "--route-hashes"):
        rep.add_argument(flag, required=True)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.cmd == "cache-identity":
        result = verify_cache(Path(args.cache), read_csv(Path(args.manifest)))
        Path(args.out).write_text(json.dumps(result["counts"], indent=1, sort_keys=True) + "\n",
                                  encoding="ascii", newline="\n")
        print("CACHE-IDENTITY " + json.dumps(result["counts"], sort_keys=True))
        return 0
    result = replay(Path(args.evidence), Path(args.frames), Path(args.ratings),
                    Path(args.archived_predictions), Path(args.fresh_predictions),
                    json.loads(Path(args.route_hashes).read_text(encoding="ascii")))
    print("REPLAY " + json.dumps({"c0_fresh": result["gate"]["c0_fresh"],
                                  "premise_false": result["gate"]["premise_false"],
                                  "reproduces": result["reproduces_archived"], "a0_rows_identical": result["fresh_vs_archived_A0"]["rows_identical"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
