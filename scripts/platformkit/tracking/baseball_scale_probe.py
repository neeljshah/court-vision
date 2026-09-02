"""Measure baseball scale validation on real clips and render what it decided.

Runs the mound chord, the landmark detector and the two-reference gate over
sampled frames of one or more clips, then writes per-clip counts and a small
set of overlay frames so the decision can be looked at rather than trusted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Optional

import cv2
import numpy as np

from domains.baseball.tracking.geometry import detect_pitch_geometry
from domains.baseball.tracking.plate_landmark import (
    VALIDATED, PlateLandmarks, ScaleValidation, chord_from_geometry,
    detect_plate_landmarks, validate_scale,
)
from domains.baseball.tracking.segmenter import detect_cut, small_gray

RED, YELLOW, CYAN, MAGENTA, GREEN = ((0, 0, 255), (0, 255, 255), (255, 255, 0),
                                     (255, 0, 255), (0, 255, 0))


def overlay(frame: np.ndarray, geometry, landmarks: PlateLandmarks,
            report: ScaleValidation, caption: str) -> np.ndarray:
    """Draw the chord, rubber, plate and chalk so a human can judge the call."""
    canvas = frame.copy()
    chord = chord_from_geometry(geometry)
    row, left, right = chord.row, chord.left, chord.right
    cv2.line(canvas, (left, row), (right, row), RED, 3)
    for run, colour in ((landmarks.rubber, YELLOW), (landmarks.plate, CYAN)):
        if run is not None:
            cv2.rectangle(canvas, (run.left, run.row - 6), (run.right, run.row + 6), colour, 2)
    for x, y in landmarks.box_corners:
        cv2.circle(canvas, (int(x), int(y)), 5, MAGENTA, 2)
    tint = GREEN if report.scale_status == VALIDATED else RED
    lines = [caption,
             "chord %.0fpx -> %.1f px/ft (red)" % (float(right - left), report.scale_px_per_ft),
             "rubber -> %s px/ft (yellow)" % (
                 "none" if report.rubber_px_per_ft is None else "%.1f" % report.rubber_px_per_ft),
             "plate -> %s px/ft (cyan), ratio %s" % (
                 "none" if report.plate_px_per_ft is None else "%.1f" % report.plate_px_per_ft,
                 "n/a" if report.perspective_ratio is None else "%.2f" % report.perspective_ratio),
             "%s: %s" % (report.scale_status.upper(), report.reason)]
    for index, text in enumerate(lines):
        cv2.putText(canvas, text, (12, 26 + 24 * index), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    tint if index == len(lines) - 1 else (255, 255, 255), 2, cv2.LINE_AA)
    return canvas


def probe_clip(path: Path, game_id: str, out_dir: Optional[Path], max_frames: int = 600,
               stride: int = 3, overlays: int = 2) -> dict[str, object]:
    """Sample one clip and return its detection, agreement and scale summary."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % path)
    scales: list[float] = []
    validated_scales: list[float] = []
    ratios: list[float] = []
    segments: dict[int, list[str]] = {}
    plate_hits = rubber_hits = processed = 0
    segment_id, in_view = 0, False
    previous: Optional[np.ndarray] = None
    saved: list[tuple[str, np.ndarray]] = []
    last_saved: dict[str, int] = {}
    source = 0
    try:
        while processed < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            if source % stride == 0:
                grey = small_gray(frame)
                cut = previous is not None and detect_cut(previous, grey)
                previous = grey
                geometry = None if cut else detect_pitch_geometry(frame)
                if geometry is None:
                    in_view = False
                else:
                    if not in_view:
                        segment_id, in_view = segment_id + 1, True
                    chord = chord_from_geometry(geometry)
                    landmarks = detect_plate_landmarks(frame, chord)
                    report = validate_scale(chord, landmarks)
                    scales.append(report.scale_px_per_ft)
                    plate_hits += landmarks.plate is not None
                    rubber_hits += landmarks.rubber is not None
                    if report.perspective_ratio is not None:
                        ratios.append(report.perspective_ratio)
                    if report.scale_status == VALIDATED:
                        validated_scales.append(report.scale_px_per_ft)
                    segments.setdefault(segment_id, []).append(report.scale_status)
                    # Balance the contact sheet across verdicts and space the
                    # samples out, so it shows rejects and not just neighbours
                    # of one easy accept.
                    verdict = report.scale_status
                    kept = sum(name.endswith("_" + verdict + ".png") for name, _ in saved)
                    if (out_dir is not None and kept < max(1, overlays // 2)
                            and source - last_saved.get(verdict, -10 ** 6) >= 300):
                        last_saved[verdict] = source
                        saved.append(("%s_f%06d_%s.png" % (game_id, source, verdict),
                                      overlay(frame, geometry, landmarks, report,
                                              "%s frame %d" % (game_id, source))))
                processed += 1
            source += 1
    finally:
        capture.release()
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, image in saved:
            cv2.imwrite(str(out_dir / name), image)
    validated_segments = [s for s, rows in segments.items() if VALIDATED in rows]
    return {
        "game_id": game_id,
        "frames_processed": processed,
        "pitch_view_frames": len(scales),
        "plate_detection_rate": round(plate_hits / len(scales), 3) if scales else None,
        "rubber_detection_rate": round(rubber_hits / len(scales), 3) if scales else None,
        "frame_agreement_rate": round(len(validated_scales) / len(scales), 3) if scales else None,
        "segments": len(segments),
        "segments_validated": len(validated_segments),
        "segment_agreement_rate": (round(len(validated_segments) / len(segments), 3)
                                   if segments else None),
        "scale_median_all": round(median(scales), 1) if scales else None,
        "scale_median_validated": round(median(validated_scales), 1) if validated_scales else None,
        "scale_min_all": round(min(scales), 1) if scales else None,
        "scale_max_all": round(max(scales), 1) if scales else None,
        "scale_min_validated": round(min(validated_scales), 1) if validated_scales else None,
        "scale_max_validated": round(max(validated_scales), 1) if validated_scales else None,
        "perspective_ratio_median": round(median(ratios), 2) if ratios else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips", nargs="+", help="paths to broadcast clips")
    parser.add_argument("--out-dir", default=None, help="directory for overlay frames")
    parser.add_argument("--max-frames", type=int, default=600)
    parser.add_argument("--stride", type=int, default=3)
    parser.add_argument("--overlays", type=int, default=2)
    args = parser.parse_args()
    out_dir = Path(args.out_dir) if args.out_dir else None
    rows = [probe_clip(Path(clip), Path(clip).stem, out_dir, args.max_frames, args.stride,
                       args.overlays) for clip in args.clips]
    print(json.dumps(rows, indent=2))
    if out_dir is not None:
        (out_dir / "summary.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
