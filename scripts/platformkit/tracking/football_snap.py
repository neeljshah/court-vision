"""Football motion-energy and snap detection at the IMAGE_PX_DECLARED rung.

Funded by docs/research/organization-sprint/FOOTBALL_POST_OCR_DECISION_2026-09-01.md
Step 1: the only football work that is legal without a field registration.
Numeral OCR is terminally rejected; nothing here reads, scales, or registers.

Every emitted row declares ``coordinate_space=image_px`` / ``calibration=none``,
so the harness's coordinate contract refuses to score it as court geometry.
No distance, scale, or metric claim may be derived from these rows.

Detection is CAUSAL with a fixed lookahead: the decision at frame ``i`` reads
only ``energy[i - BASELINE_FRAMES .. i + STEP_FRAMES]``. Truncating the clip at
frame N therefore leaves every event at ``frame + STEP_FRAMES < N`` bit-identical
-- see ``test_football_snap.py::test_truncation_invariance``. A whole-clip
percentile threshold would have been simpler and would NOT have this property.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator, Optional, Sequence, Union

import cv2
import numpy as np
import pandas as pd

from scripts.platformkit.coordinate_provenance import (
    stamp_image_space_rows, write_tracking_csv)

SCHEMA = ("frame", "track_id", "cls", "x", "y", "ts_s", "energy", "confidence")
MOTION_CLS, SNAP_CLS = "motion_energy", "snap"

# Pre-registered detector constants. Fixed before any measurement; the football
# memo bans moving a threshold to make a result pass.
PROC_WIDTH = 320          # frames are diffed at this width; centroids scale back
BASELINE_FRAMES = 90      # trailing window (~3 s) estimating the quiet level
QUIET_FRAMES = 12         # sustained pre-snap stillness required, ~0.4 s
STEP_FRAMES = 8           # sustained post-snap motion required, ~0.27 s
STEP_RATIO = 2.5          # post/quiet median ratio that counts as a motion step
ENERGY_FLOOR = 1.0        # grey-level floor; stops a ratio blowing up on stillness
REFRACTORY_S = 4.0        # a play lasts longer than this; one snap per window
CUT_ENERGY = 40.0         # a whole-frame jump this large is a camera cut, not a snap


def _gray(frame: np.ndarray) -> np.ndarray:
    """Downscale to PROC_WIDTH and grey. Diff noise is the enemy, not detail."""
    scale = PROC_WIDTH / float(frame.shape[1])
    small = cv2.resize(frame, (PROC_WIDTH, max(1, int(round(frame.shape[0] * scale)))))
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


def _energy_and_centroid(previous: np.ndarray, current: np.ndarray) -> tuple[float, float, float]:
    """Return (median abs-diff, cx, cy) with the centroid in PROC_WIDTH pixels.

    The median is the same statistic as
    ``domains.football.tracking.adapter.FootballAdapter.motion_magnitude``
    (asserted in the test); the diff array is reused for the centroid instead of
    being recomputed.
    """
    diff = cv2.absdiff(previous, current)
    moments = cv2.moments(diff)
    if moments["m00"] > 0:
        centre = (moments["m10"] / moments["m00"], moments["m01"] / moments["m00"])
    else:
        centre = (diff.shape[1] / 2.0, diff.shape[0] / 2.0)
    return float(np.median(diff)), float(centre[0]), float(centre[1])


def frame_energy(frames: Iterator[np.ndarray]) -> pd.DataFrame:
    """Per-frame motion energy plus the motion centroid, in source pixels.

    Frame 0 has no predecessor and is not emitted; energy is a pair statistic.
    """
    rows, previous, source_width = [], None, None
    for index, frame in enumerate(frames):
        if source_width is None:
            source_width = frame.shape[1]
        small = _gray(frame)
        if previous is not None:
            energy, cx, cy = _energy_and_centroid(previous, small)
            back = source_width / float(PROC_WIDTH)
            rows.append({"frame": index, "energy": energy,
                         "x": cx * back, "y": cy * back})
        previous = small
    return pd.DataFrame(rows, columns=["frame", "energy", "x", "y"])


def detect_snaps(energy: Sequence[float], fps: float,
                 gate: Optional[Sequence[bool]] = None) -> list[dict]:
    """Rising motion steps out of sustained stillness. Causal + fixed lookahead.

    ``energy[i]`` is the motion between frames i-1 and i, so index i in this
    sequence is the frame the caller labelled i in ``frame_energy``.

    ``gate`` is an optional per-position acceptance mask aligned to ``energy``
    (see ``football_fieldview.field_view_gate``): candidates outside it are
    dropped. It is a precondition on the input shot, not a threshold change --
    no detector constant moves when a gate is supplied.
    """
    series = np.asarray(energy, dtype=float)
    events: list[dict] = []
    refractory = max(1, int(round(REFRACTORY_S * fps)))
    last_fired = -refractory
    for i in range(QUIET_FRAMES, len(series) - STEP_FRAMES):
        if i - last_fired < refractory:
            continue
        if gate is not None and not gate[i]:
            continue
        quiet = float(np.median(series[max(0, i - QUIET_FRAMES):i]))
        after = float(np.median(series[i:i + STEP_FRAMES]))
        base_lo = max(0, i - BASELINE_FRAMES)
        baseline = float(np.median(series[base_lo:i])) if i > base_lo else quiet
        level = max(quiet, ENERGY_FLOOR)
        if after < STEP_RATIO * level:
            continue
        if float(series[i:i + STEP_FRAMES].max()) >= CUT_ENERGY:
            continue  # camera cut / replay wipe, not a snap
        if quiet > max(baseline, ENERGY_FLOOR):
            continue  # the "quiet" run is not quiet relative to the clip
        events.append({
            "frame": i, "ts_s": i / fps,
            "confidence": float(min(1.0, (after / level - STEP_RATIO) / STEP_RATIO)),
            "energy": after, "quiet": quiet,
        })
        last_fired = i
    return events


def _rows(energy_table: pd.DataFrame, events: Sequence[dict], fps: float) -> pd.DataFrame:
    """Tracking rows for both channels, image-pixel declared."""
    motion = energy_table.assign(
        track_id=0, cls=MOTION_CLS, ts_s=energy_table["frame"] / fps, confidence=np.nan)
    by_frame = energy_table.set_index("frame")
    snaps = pd.DataFrame([{
        "frame": event["frame"], "track_id": 0, "cls": SNAP_CLS,
        "x": float(by_frame.loc[event["frame"], "x"]),
        "y": float(by_frame.loc[event["frame"], "y"]),
        "ts_s": event["ts_s"], "energy": event["energy"],
        "confidence": event["confidence"],
    } for event in events], columns=list(SCHEMA))
    combined = pd.concat([motion.loc[:, list(SCHEMA)], snaps], ignore_index=True)
    return stamp_image_space_rows(combined)


def _decode(path: Union[str, Path], start_frame: int, max_frames: Optional[int]) -> Iterator[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % path)
    try:
        if start_frame:
            capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        emitted = 0
        while max_frames is None or emitted < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            yield frame
            emitted += 1
    finally:
        capture.release()


def video_fps(path: Union[str, Path]) -> float:
    capture = cv2.VideoCapture(str(path))
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
    finally:
        capture.release()
    return fps if fps > 1.0 else 30.0


def process_video(path: Union[str, Path], start_frame: int = 0,
                  max_frames: Optional[int] = None) -> tuple[pd.DataFrame, list[dict]]:
    """Return (image_px tracking rows, snap events). Frame numbers are clip-local."""
    fps = video_fps(path)
    energy_table = frame_energy(_decode(path, start_frame, max_frames))
    events = detect_snaps(energy_table["energy"].tolist(), fps)
    for event in events:
        event["source_frame"] = event["frame"] + start_frame
    return _rows(energy_table, events, fps), events


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--tag", default=None)
    args = parser.parse_args(argv)

    rows, events = process_video(args.video, args.start_frame, args.max_frames)
    out = Path(args.out_dir)
    tag = args.tag or Path(args.video).stem
    write_tracking_csv(rows, out / ("%s_image_px.csv" % tag), SCHEMA)
    payload = {
        "video": str(args.video), "tag": tag,
        "fps": video_fps(args.video), "start_frame": args.start_frame,
        "frames_with_energy": int(len(rows[rows["cls"] == MOTION_CLS])),
        "coordinate_space": "image_px", "rung": "IMAGE_PX_DECLARED",
        "constants": {"PROC_WIDTH": PROC_WIDTH, "BASELINE_FRAMES": BASELINE_FRAMES,
                      "QUIET_FRAMES": QUIET_FRAMES, "STEP_FRAMES": STEP_FRAMES,
                      "STEP_RATIO": STEP_RATIO, "ENERGY_FLOOR": ENERGY_FLOOR,
                      "REFRACTORY_S": REFRACTORY_S, "CUT_ENERGY": CUT_ENERGY},
        "snaps": events,
    }
    (out / ("%s_snaps.json" % tag)).write_text(json.dumps(payload, indent=2))
    print("%s: %d frames, %d snaps" % (tag, payload["frames_with_energy"], len(events)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
