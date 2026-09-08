"""G302 attempt 2: prove a re-acquired source IS the population a prior row measured.

Attempt 1 was rejected because both named sources were lost in the 2026-09-07 pod
rebuild and substitutes were measured instead. Re-acquiring a source is only useful
if its identity can be shown, so this module runs the three checks the spec's
VERSION 2026-09-07b amendment names:

  byte hash      -- SHA-256 against the value master records for that source;
  container      -- resolution equal and duration within 1 s of the recorded facts;
  reproduction   -- re-render the prior row's committed blind crops from this file at
                    the recorded source frame and footpoint and report the mean
                    absolute pixel difference against the committed JPEGs.

Reproduction is the strongest of the three: a file that reproduces all 72 committed
crops at JPEG-requantization distance IS that row's population, frame for frame.
Measurement only -- nothing here is a detector, a gate or a production change.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from scripts.platformkit.tracking.g302_amateur_resolution_attribution import (
    CROP_H, CROP_W, crop, scan, sha256)

MARKER_MASK_PX = 48  # the committed crops carry a footpoint marker; never compare it
EVIDENCE = Path("docs/evidence/tracking")
PRIOR: dict[str, dict[str, Any]] = {
    "g273": {"artifact": EVIDENCE / "g273_detector_precision_blind_sample_artifact",
             "recorded": {"bytes": 2931985407, "resolution_px": [1920, 1080], "fps": 30.0}},
    "g280b": {"artifact": EVIDENCE / "g280_amateur_footage_trackability_artifact" / "blind_packet",
              # master records TWO durations for this one file and both are kept verbatim:
              # run_1/run_manifest.json source_duration = 124.3 (frames / fps) and
              # g280_pod_preflight.json source_duration_seconds = 120.1 (container).
              "recorded": {"bytes": 24523745, "resolution_px": [1280, 720], "frames": 3729,
                           "duration_s_recorded": {"g280_run_1_manifest.source_duration": 124.3,
                                                   "g280_pod_preflight.source_duration_seconds": 120.1},
                           "sha256": "773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea"}},
}


def prior_rows(row: str, root: Path) -> tuple[list[dict[str, Any]], Path]:
    """The prior row's committed (blind_index, source_frame, footpoint) and its render dir."""
    artifact = root / PRIOR[row]["artifact"]
    if row == "g273":
        summary = json.loads((artifact / "measurement_summary.json").read_text(encoding="ascii"))
        rows = [{"blind_index": r["blind_index"], "source_frame": r["source_frame"],
                 "foot_x_px": r["foot_x_px"], "foot_y_px": r["foot_y_px"]}
                for r in summary["unblinded_rows"]]
    else:
        rows = [{"blind_index": r["blind_index"], "source_frame": r["frame"],
                 "foot_x_px": r["x"], "foot_y_px": r["y"]}
                for r in json.loads((artifact / "unblind_map.json").read_text(encoding="ascii"))]
    return rows, artifact / "blind_renders"


def reproduce(video: Path, rows: list[dict[str, Any]], renders: Path, offset: int = 0) -> list[float]:
    """Mean absolute pixel difference per committed crop, marker patch excluded."""
    by_frame: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_frame.setdefault(row["source_frame"] + offset, []).append(row)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not open " + str(video))
    half, out = MARKER_MASK_PX // 2, []
    for source_frame, image in scan(capture, sorted(by_frame)):
        for row in by_frame[source_frame]:
            mine = crop(image, row["foot_x_px"], row["foot_y_px"]).astype(np.int16)
            theirs = cv2.imread(str(renders / ("blind_%03d.jpg" % row["blind_index"])))
            if theirs is None:
                raise RuntimeError("missing committed render for blind_%03d" % row["blind_index"])
            diff = np.abs(mine - theirs.astype(np.int16))
            diff[CROP_H // 2 - half:CROP_H // 2 + half, CROP_W // 2 - half:CROP_W // 2 + half] = 0
            out.append(float(diff.mean()))
    capture.release()
    return out


def check(video: Path, row: str, root: Path, offset: int = 0) -> dict[str, Any]:
    """The full identity table for one re-acquired source against one prior row."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not open " + str(video))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    observed = {"absolute_path": str(video.resolve()), "bytes": video.stat().st_size,
                "resolution_px": [int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                                  int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))],
                "fps": fps, "frames": int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
                "duration_s": round(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) / fps, 3) if fps else None,
                "sha256": sha256(video)}
    capture.release()
    recorded = PRIOR[row]["recorded"]
    rows, renders = prior_rows(row, root)
    mads = reproduce(video, rows, renders, offset)
    byte_hash = ("IDENTICAL" if observed["sha256"] == recorded.get("sha256")
                 else "DIFFERENT (re-encode or remux; not a failure)")
    deltas = {name: round(abs(observed["duration_s"] - value), 3)
              for name, value in recorded.get("duration_s_recorded", {}).items()}
    matched = [name for name, delta in deltas.items() if delta <= 1.0]
    return {"prior_row": row, "frame_offset": offset, "observed": observed, "recorded": recorded,
            "byte_hash": byte_hash,
            "resolution_equal": observed["resolution_px"] == recorded["resolution_px"],
            "frames_equal": ("NOT RECORDED" if "frames" not in recorded
                             else observed["frames"] == recorded["frames"]),
            "duration_within_1s": ("NOT RECORDED" if not deltas else bool(matched)),
            "duration_deltas_s": deltas, "duration_matched_record": matched,
            "reproduction": {"crops": len(mads), "marker_mask_px": MARKER_MASK_PX,
                             "mad_mean": round(float(np.mean(mads)), 4),
                             "mad_max": round(float(np.max(mads)), 4),
                             "mad_min": round(float(np.min(mads)), 4),
                             "crops_under_3_mad": int(sum(m < 3.0 for m in mads)),
                             "per_crop_mad": [round(m, 4) for m in mads]},
            "verdict": ("SAME POPULATION" if sum(m < 3.0 for m in mads) == len(mads)
                        else "NOT ESTABLISHED")}


def main() -> None:
    parser = argparse.ArgumentParser(description="G302 attempt-2 source identity check")
    parser.add_argument("--video", type=Path, action="append", required=True,
                        help="repeat once per --row, in the same order")
    parser.add_argument("--row", choices=tuple(PRIOR), action="append", required=True)
    parser.add_argument("--name", action="append", help="report basename; defaults to the row id")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--offset", type=int, action="append")
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    if len(args.video) != len(args.row):
        parser.error("--video and --row must be repeated the same number of times")
    offsets = args.offset or [0] * len(args.row)
    names = args.name or list(args.row)
    reports = {}
    for video, row, offset, name in zip(args.video, args.row, offsets, names):
        reports[name] = check(video, row, args.root, offset)
        if args.out_dir:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            (args.out_dir / (name + ".json")).write_text(
                json.dumps(reports[name], indent=2) + chr(10), encoding="ascii")
    print(json.dumps(reports, sort_keys=True))


if __name__ == "__main__":
    main()
