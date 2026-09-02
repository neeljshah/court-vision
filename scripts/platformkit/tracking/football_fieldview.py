"""Field-view gate for football at the IMAGE_PX_DECLARED rung.

The football snap detector (``football_snap.py``) measured 3/20 hand-verified
precision on real broadcasts -- 13 of 20 detections were camera cuts to
sidelines, studio shots and graphic bumpers. See
``docs/evidence/tracking/football_imagepx_snap_2026-09-01.md``: whole-frame
motion energy measures the CAMERA, and football has no field-view test at this
rung to say which shot the camera is even pointed at.

This module is that missing test, built only from cheap image statistics:
turf-green ratio, the count of long near-parallel lines (yard lines), edge
density (a full-frame graphic card is flat), and shot segmentation with a
minimum-scene-length hysteresis. It is a PRECONDITION ON THE INPUT, not a gate
on a metric's own bound -- it never touches a threshold inside the detector, so
it is not the tautological-gate pattern.

Nothing here reads, scales or registers anything. Emitted rows declare
``coordinate_space=image_px`` / ``calibration=none`` and stay unscorable as
field geometry.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence, Union

import cv2
import numpy as np
import pandas as pd

from scripts.platformkit.coordinate_provenance import (
    stamp_image_space_rows, write_tracking_csv)
from scripts.platformkit.tracking import football_snap

FIELD_CLS = "field_view"
SCHEMA = football_snap.SCHEMA + ("is_field_view",)

# Pre-registered constants. Fixed against the synthetic shot types in
# test_football_fieldview.py BEFORE any real footage was scored; the football
# memo bans moving a threshold after seeing a measurement.
PROC_WIDTH = 320
GREEN_HUE = (35, 90)       # OpenCV hue is 0..179; turf sits inside this band
GREEN_SAT_MIN, GREEN_VAL_MIN = 40, 40
GREEN_MIN = 0.25           # a wide field view is mostly turf
GREEN_STRONG = 0.45        # green enough to stand alone when lines do not resolve
LINE_MIN, LINE_STRONG = 2, 6
PARALLEL_DEG = 15.0        # yard lines converge slightly under perspective
LONG_LINE_FRAC = 0.25      # a yard line spans at least a quarter of the frame
EDGE_MIN = 0.015           # a flat full-frame graphic card has almost no edges
CUT_MEAN = 25.0            # mean abs grey diff only a shot change produces
MIN_SCENE_FRAMES = 15      # shorter than this is a flicker, never a field view
CUT_GUARD_FRAMES = 15      # no snap accepted within this of a shot boundary


def _small(frame: np.ndarray) -> np.ndarray:
    scale = PROC_WIDTH / float(frame.shape[1])
    return cv2.resize(frame, (PROC_WIDTH, max(1, int(round(frame.shape[0] * scale)))))


def _parallel_lines(edges: np.ndarray) -> int:
    """Largest set of long segments whose angles agree within PARALLEL_DEG."""
    segments = cv2.HoughLinesP(edges, 1, np.pi / 180.0, threshold=40,
                               minLineLength=int(LONG_LINE_FRAC * edges.shape[1]),
                               maxLineGap=8)
    if segments is None:
        return 0
    segments = segments.reshape(-1, segments.shape[-1])
    x1, y1, x2, y2 = (segments[:, 0, i].astype(float) for i in range(4))
    angle = np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180.0
    # ponytail: O(n^2) over long segments only -- tens per frame, not thousands.
    gap = np.abs(angle[:, None] - angle[None, :])
    return int((np.minimum(gap, 180.0 - gap) <= PARALLEL_DEG).sum(axis=1).max())


def frame_features(frame: np.ndarray) -> tuple[dict, np.ndarray]:
    """Cheap per-frame shot statistics, plus the grey frame for cut detection."""
    small = _small(frame)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (GREEN_HUE[0], GREEN_SAT_MIN, GREEN_VAL_MIN),
                       (GREEN_HUE[1], 255, 255))
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(grey, 60, 160)
    return ({"green": float(mask.mean() / 255.0),
             "edges": float(edges.mean() / 255.0),
             "lines": _parallel_lines(edges)}, grey)


def _feature_stream(frames: Iterable[np.ndarray], sink: list) -> Iterator[np.ndarray]:
    """Pass frames through, appending each frame's features to ``sink``.

    One decode feeds two consumers: this gate and football_snap.frame_energy.
    """
    previous = None
    for frame in frames:
        features, grey = frame_features(frame)
        features["cut_diff"] = (0.0 if previous is None
                                else float(cv2.absdiff(previous, grey).mean()))
        previous = grey
        sink.append(features)
        yield frame


def _table(sink: Sequence[dict]) -> pd.DataFrame:
    """Per-frame feature table with the raw (pre-hysteresis) verdict and score."""
    table = pd.DataFrame(list(sink), columns=["green", "edges", "lines", "cut_diff"])
    table.insert(0, "frame", np.arange(len(table)))
    table["score"] = (0.7 * np.minimum(table["green"] / GREEN_STRONG, 1.0)
                      + 0.3 * np.minimum(table["lines"] / float(LINE_STRONG), 1.0))
    table["raw"] = ((table["green"] >= GREEN_MIN) & (table["edges"] >= EDGE_MIN)
                    & ((table["lines"] >= LINE_MIN) | (table["green"] >= GREEN_STRONG)))
    return table


def scan(frames: Iterable[np.ndarray]) -> pd.DataFrame:
    """Feature table for a frame sequence (decode-once helper for callers)."""
    sink: list = []
    for _ in _feature_stream(frames, sink):
        pass
    return _table(sink)


def scene_bounds(cut_diff: Sequence[float]) -> list[tuple[int, int]]:
    """Half-open [start, end) shot spans. A cut is a whole-frame grey jump."""
    diff = np.asarray(cut_diff, dtype=float)
    starts = [0] + [i for i in range(1, len(diff)) if diff[i] >= CUT_MEAN]
    starts.append(len(diff))
    return [(starts[i], starts[i + 1]) for i in range(len(starts) - 1)]


def field_view_gate(table: pd.DataFrame) -> np.ndarray:
    """Per-frame acceptance mask: inside a stable field-view shot, off the seams.

    Hysteresis is at the SHOT level, not the frame level: a shot is field view
    only if it lasts MIN_SCENE_FRAMES and a majority of its frames pass the raw
    test, and the CUT_GUARD_FRAMES either side of a shot boundary are never
    accepted -- that boundary is precisely where a camera cut fakes a snap.
    """
    gate = np.zeros(len(table), dtype=bool)
    raw = table["raw"].to_numpy()
    for start, end in scene_bounds(table["cut_diff"].to_numpy()):
        if end - start < MIN_SCENE_FRAMES or raw[start:end].mean() <= 0.5:
            continue
        gate[start + CUT_GUARD_FRAMES:max(start, end - CUT_GUARD_FRAMES)] = True
    return gate


def _rows(table: pd.DataFrame, gate: np.ndarray, fps: float) -> pd.DataFrame:
    """Field-view rows, image-pixel declared. x/y are NaN: no location claimed."""
    rows = pd.DataFrame({
        "frame": table["frame"], "track_id": 0, "cls": FIELD_CLS,
        "x": np.nan, "y": np.nan, "ts_s": table["frame"] / fps,
        "energy": table["green"], "confidence": table["score"],
        "is_field_view": gate,
    }, columns=list(SCHEMA))
    return stamp_image_space_rows(rows)


def process_video(path: Union[str, Path], start_frame: int = 0,
                  max_frames: Optional[int] = None) -> tuple[pd.DataFrame, dict]:
    """Gate + snap detection in ONE decode pass. Returns (rows, result dict)."""
    fps = football_snap.video_fps(path)
    sink: list = []
    energy = football_snap.frame_energy(
        _feature_stream(football_snap._decode(path, start_frame, max_frames), sink))
    table = _table(sink)
    gate = field_view_gate(table)
    series = energy["energy"].tolist()
    # frame_energy skips frame 0 (energy is a pair statistic), so position j of
    # the energy series is absolute frame j+1; shift the mask to line them up.
    ungated = football_snap.detect_snaps(series, fps)
    gated = football_snap.detect_snaps(series, fps, gate=gate[1:])
    result = {
        "video": str(path), "fps": fps, "start_frame": start_frame,
        "frames": int(len(table)), "coordinate_space": "image_px",
        "rung": "IMAGE_PX_DECLARED",
        "field_view_frames": int(gate.sum()),
        "field_view_fraction": float(gate.mean()) if len(gate) else 0.0,
        "scenes": len(scene_bounds(table["cut_diff"].to_numpy())),
        "constants": {"GREEN_MIN": GREEN_MIN, "GREEN_STRONG": GREEN_STRONG,
                      "LINE_MIN": LINE_MIN, "EDGE_MIN": EDGE_MIN,
                      "CUT_MEAN": CUT_MEAN, "MIN_SCENE_FRAMES": MIN_SCENE_FRAMES,
                      "CUT_GUARD_FRAMES": CUT_GUARD_FRAMES},
        "snaps_ungated": len(ungated), "snaps_gated": len(gated),
        "snaps": gated,
    }
    return _rows(table, gate, fps), result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Field-view gated football snaps.")
    parser.add_argument("video")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--tag", default=None)
    args = parser.parse_args(argv)

    rows, result = process_video(args.video, args.start_frame, args.max_frames)
    out = Path(args.out_dir)
    tag = args.tag or Path(args.video).stem
    result["tag"] = tag
    write_tracking_csv(rows, out / ("%s_fieldview_image_px.csv" % tag), SCHEMA)
    (out / ("%s_gated_snaps.json" % tag)).write_text(json.dumps(result, indent=2))
    print("%s: %d frames, %d scenes, field_view %.1f%%, snaps %d -> %d"
          % (tag, result["frames"], result["scenes"],
             100.0 * result["field_view_fraction"],
             result["snaps_ungated"], result["snaps_gated"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
