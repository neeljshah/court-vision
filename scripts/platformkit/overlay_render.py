"""Render a private side-by-side broadcast and tracking evidence video."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from scripts.platformkit.tracking_harness import SPORTS

_PANEL_WIDTH = 960
_PANEL_HEIGHT = 540
_TICKER_HEIGHT = 48
_ANNOTATION_CARRY_FRAMES = 5
_FOOTER_HEIGHT = 52
_PADDING = 36


# ---------------------------------------------------------------------------
# Court-view panel. These four helpers used to be imported from demo_render;
# 57625b81b rewrote that module onto a different API (color_for /
# draw_court_inset, which paints into an existing frame instead of returning a
# panel), leaving this file's import dangling. This is the only consumer, so
# the helpers moved here verbatim rather than reviving demo_render's old API.
# ---------------------------------------------------------------------------

def _track_color(track_id: object) -> tuple[int, int, int]:
    """Return a stable bright BGR color for a track identifier."""
    digest = hashlib.sha256(str(track_id).encode("utf-8")).digest()
    return tuple(80 + value % 176 for value in digest[:3])


def _court_geometry(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x0, x1, y0, y1 = bounds
    available_width = _PANEL_WIDTH - 2 * _PADDING
    available_height = _PANEL_HEIGHT - _FOOTER_HEIGHT - 2 * _PADDING
    scale = min(available_width / (x1 - x0), available_height / (y1 - y0))
    court_width, court_height = (x1 - x0) * scale, (y1 - y0) * scale
    left = (_PANEL_WIDTH - court_width) / 2
    top = (_PANEL_HEIGHT - _FOOTER_HEIGHT - court_height) / 2
    return left, top, scale, court_height


def _point(x: float, y: float, bounds: tuple[float, float, float, float]) -> tuple[int, int]:
    x0, _, y0, _ = bounds
    left, top, scale, court_height = _court_geometry(bounds)
    return round(left + (x - x0) * scale), round(top + court_height - (y - y0) * scale)


def _draw_frame(
    rows: pd.DataFrame,
    bounds: tuple[float, float, float, float],
    ball_trail: deque[tuple[int, int]],
    footer: str,
) -> np.ndarray:
    image = np.full((_PANEL_HEIGHT, _PANEL_WIDTH, 3), (21, 25, 31), dtype=np.uint8)
    x0, x1, y0, y1 = bounds
    left, top, scale, court_height = _court_geometry(bounds)
    right, bottom = round(left + (x1 - x0) * scale), round(top + court_height)
    cv2.rectangle(image, (round(left), round(top)), (right, bottom), (235, 235, 235), 2)
    mid_x = round(left + (x1 - x0) * scale / 2)
    cv2.line(image, (mid_x, round(top)), (mid_x, bottom), (235, 235, 235), 1)

    valid = rows.dropna(subset=["x", "y"])
    for row in valid[valid["cls"] != "ball"].itertuples(index=False):
        cv2.circle(image, _point(float(row.x), float(row.y), bounds), 7, _track_color(row.track_id), -1)

    balls = valid[valid["cls"] == "ball"]
    if not balls.empty:
        ball = balls.iloc[-1]
        ball_trail.append(_point(float(ball["x"]), float(ball["y"]), bounds))
    for index in range(1, len(ball_trail)):
        cv2.line(image, ball_trail[index - 1], ball_trail[index], (0, 190, 255), 2)
    if ball_trail:
        cv2.circle(image, ball_trail[-1], 6, (0, 255, 255), -1)

    cv2.putText(image, footer, (20, _PANEL_HEIGHT - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (235, 235, 235), 1, cv2.LINE_AA)
    return image


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
