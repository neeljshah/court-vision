"""Render a rights-safe court or pitch animation from tracking CSV data.

The renderer only draws normalized tracking coordinates. It never reads or
embeds broadcast-video pixels.
"""
from __future__ import annotations

import argparse
import hashlib
from collections import deque
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import pandas as pd

from scripts.platformkit.tracking_harness import SPORTS

_WIDTH = 960
_HEIGHT = 540
_FOOTER_HEIGHT = 52
_PADDING = 36
_BALL_TRAIL = 10


def _track_color(track_id: object) -> tuple[int, int, int]:
    """Return a stable bright BGR color for a track identifier."""
    digest = hashlib.sha256(str(track_id).encode("utf-8")).digest()
    return tuple(80 + value % 176 for value in digest[:3])


def _court_geometry(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x0, x1, y0, y1 = bounds
    available_width = _WIDTH - 2 * _PADDING
    available_height = _HEIGHT - _FOOTER_HEIGHT - 2 * _PADDING
    scale = min(available_width / (x1 - x0), available_height / (y1 - y0))
    court_width, court_height = (x1 - x0) * scale, (y1 - y0) * scale
    left = (_WIDTH - court_width) / 2
    top = (_HEIGHT - _FOOTER_HEIGHT - court_height) / 2
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
    image = np.full((_HEIGHT, _WIDTH, 3), (21, 25, 31), dtype=np.uint8)
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

    cv2.putText(image, footer, (20, _HEIGHT - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 235, 235), 1, cv2.LINE_AA)
    return image


def _write_gif(path: Path, frames: Iterable[np.ndarray], fps: int) -> bool:
    try:
        import imageio.v2 as imageio
    except ImportError:
        return False
    rgb_frames = [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in frames]
    imageio.mimsave(path, rgb_frames, duration=1 / fps)
    return True


def render_csv(
    csv_path: str | Path,
    sport: str,
    out_path: str | Path | None = None,
    gif_path: str | Path | None = None,
    fps: int = 30,
    max_seconds: float = 20,
) -> int:
    """Render CSV tracking rows, returning the number of frames written."""
    if sport not in SPORTS:
        raise ValueError(f"Unsupported sport: {sport}")
    if fps <= 0 or max_seconds <= 0:
        raise ValueError("fps and max_seconds must be positive")
    if out_path is None and gif_path is None:
        raise ValueError("Specify --out and/or --gif")

    data = pd.read_csv(csv_path, low_memory=False)
    aliases = {"player_id": "track_id", "ft_x": "x", "ft_y": "y"}
    data = data.rename(columns={k: v for k, v in aliases.items()
                                if k in data.columns and v not in data.columns})
    if "cls" not in data.columns:
        data = data.assign(cls="player")
    required = {"frame", "track_id", "cls", "x", "y"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {', '.join(sorted(missing))}")
    frame_numbers = sorted(data["frame"].dropna().unique())[: int(fps * max_seconds)]
    game_id = str(data["game_id"].iloc[0]) if "game_id" in data and not data.empty else Path(csv_path).stem
    footer = f"{sport} {game_id} CourtVision tracking demo"
    bounds = tuple(SPORTS[sport]["bounds"])
    video = None
    if out_path is not None:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        video = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (_WIDTH, _HEIGHT))
        if not video.isOpened():
            raise RuntimeError(f"Could not open video output: {out}")

    gif_frames: list[np.ndarray] = []
    trail: deque[tuple[int, int]] = deque(maxlen=_BALL_TRAIL)
    try:
        for frame_number in frame_numbers:
            image = _draw_frame(data[data["frame"] == frame_number], bounds, trail, footer)
            if video is not None:
                video.write(image)
            if gif_path is not None:
                gif_frames.append(image)
    finally:
        if video is not None:
            video.release()
    if gif_path is not None and gif_frames:
        gif = Path(gif_path)
        gif.parent.mkdir(parents=True, exist_ok=True)
        _write_gif(gif, gif_frames, fps)
    return len(frame_numbers)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a tracking-only sports demo.")
    parser.add_argument("--csv", required=True, help="Normalized tracking CSV path")
    parser.add_argument("--sport", required=True, choices=sorted(SPORTS))
    parser.add_argument("--out", help="MP4 output path")
    parser.add_argument("--gif", help="Optional GIF output path")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--max-seconds", type=float, default=20)
    args = parser.parse_args()
    rendered = render_csv(args.csv, args.sport, args.out, args.gif, args.fps, args.max_seconds)
    print(f"Rendered {rendered} tracking frames")


if __name__ == "__main__":
    main()
