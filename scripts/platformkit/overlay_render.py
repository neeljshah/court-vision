"""Render a private side-by-side broadcast and tracking evidence video."""
from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from scripts.platformkit.demo_render import _draw_frame, _track_color
from scripts.platformkit.tracking_harness import SPORTS

_PANEL_WIDTH = 960
_PANEL_HEIGHT = 540
_TICKER_HEIGHT = 48
_ANNOTATION_CARRY_FRAMES = 5


def _load_homography(path: str | Path | None) -> np.ndarray | None:
    """Load an image-to-court homography and return its court-to-image inverse."""
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    matrix = payload
    if isinstance(payload, dict):
        matrix = next((payload[key] for key in ("homography", "H", "matrix") if key in payload), None)
    array = np.asarray(matrix, dtype=np.float64)
    if array.shape != (3, 3):
        raise ValueError("Homography JSON must contain a 3x3 image-to-court matrix")
    return np.linalg.inv(array)


def _frame_rows(data: pd.DataFrame, frame: int) -> pd.DataFrame:
    matches = data[data["frame"] == frame]
    return matches if not matches.empty else data.iloc[0:0]


def _annotate_video(
    image: np.ndarray, rows: pd.DataFrame, homography: np.ndarray | None
) -> np.ndarray:
    result = image.copy()
    has_boxes = {"bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"}.issubset(rows.columns)
    if has_boxes:
        for row in rows.dropna(subset=["bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"]).itertuples():
            color = _track_color(row.track_id)
            p1 = (round(row.bbox_x1), round(row.bbox_y1))
            p2 = (round(row.bbox_x2), round(row.bbox_y2))
            cv2.rectangle(result, p1, p2, color, 2)
            cv2.putText(result, str(row.track_id), (p1[0], max(14, p1[1] - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    elif homography is not None and {"x", "y"}.issubset(rows.columns):
        points = rows.dropna(subset=["x", "y"])[["x", "y"]].to_numpy(np.float32).reshape(-1, 1, 2)
        if len(points):
            pixels = cv2.perspectiveTransform(points, homography).reshape(-1, 2)
            valid = rows.dropna(subset=["x", "y"]).itertuples()
            for row, point in zip(valid, pixels):
                center = tuple(np.rint(point).astype(int))
                color = _track_color(row.track_id)
                cv2.circle(result, center, 5, color, -1)
                cv2.putText(result, str(row.track_id), (center[0] + 6, center[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return result


def _ticker(sport: str, frame: int, rows: pd.DataFrame) -> np.ndarray:
    strip = np.full((_TICKER_HEIGHT, _PANEL_WIDTH * 2, 3), (21, 25, 31), dtype=np.uint8)
    players = rows[rows["cls"] != "ball"]["track_id"].nunique() if not rows.empty else 0
    ball = "tracked" if not rows.empty and (rows["cls"] == "ball").any() else "unavailable"
    text = f"{sport}  frame {frame}  players tracked {players}  ball {ball}"
    cv2.putText(strip, text, (20, 31), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (235, 235, 235), 1, cv2.LINE_AA)
    return strip


def render_overlay(
    video_path: str | Path,
    csv_path: str | Path,
    sport: str,
    out_path: str | Path,
    start_frame: int = 0,
    max_seconds: float = 60,
    stride: int = 1,
    homography_path: str | Path | None = None,
) -> int:
    """Render synchronized broadcast and court-diagram panels; return output frames."""
    if sport not in SPORTS:
        raise ValueError(f"Unsupported sport: {sport}")
    if start_frame < 0 or max_seconds <= 0 or stride <= 0:
        raise ValueError("start-frame, max-seconds, and stride must be positive")
    data = pd.read_csv(csv_path, low_memory=False)
    # accept raw NBA/WNBA pipeline schema (player_id/ft_x/ft_y)
    aliases = {"player_id": "track_id", "ft_x": "x", "ft_y": "y"}
    data = data.rename(columns={k: v for k, v in aliases.items()
                                if k in data.columns and v not in data.columns})
    if "cls" not in data.columns:
        data = data.assign(cls="player")
    required = {"frame", "track_id", "cls", "x", "y"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {', '.join(sorted(missing))}")
    data["frame"] = pd.to_numeric(data["frame"], errors="coerce")
    data = data.dropna(subset=["frame"]).copy()
    data["frame"] = data["frame"].astype(int)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    maximum = max(1, int(fps * max_seconds))
    capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps / stride, (_PANEL_WIDTH * 2, _PANEL_HEIGHT + _TICKER_HEIGHT))
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"Could not open video output: {out}")
    inverse_homography = _load_homography(homography_path)
    bounds = tuple(SPORTS[sport]["bounds"])
    trail: deque[tuple[int, int]] = deque(maxlen=10)
    last_rows = data.iloc[0:0]
    last_annotation_frame = -_ANNOTATION_CARRY_FRAMES - 1
    count = 0
    try:
        for offset in range(maximum):
            ok, frame = capture.read()
            if not ok:
                break
            frame_number = start_frame + offset
            exact = _frame_rows(data, frame_number)
            if not exact.empty:
                last_rows, last_annotation_frame = exact, frame_number
            rows = last_rows if frame_number - last_annotation_frame <= _ANNOTATION_CARRY_FRAMES else data.iloc[0:0]
            if offset % stride:
                continue
            left = cv2.resize(_annotate_video(frame, rows, inverse_homography), (_PANEL_WIDTH, _PANEL_HEIGHT))
            right = _draw_frame(rows, bounds, trail, f"{sport} court view")
            writer.write(np.vstack((np.hstack((left, right)), _ticker(sport, frame_number, rows))))
            count += 1
    finally:
        capture.release()
        writer.release()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Render private broadcast tracking evidence.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--sport", required=True, choices=sorted(SPORTS))
    parser.add_argument("--out", required=True)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--max-seconds", type=float, default=60)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--homography")
    args = parser.parse_args()
    rendered = render_overlay(args.video, args.csv, args.sport, args.out, args.start_frame, args.max_seconds, args.stride, args.homography)
    print(f"Rendered {rendered} evidence frames")


if __name__ == "__main__":
    main()
