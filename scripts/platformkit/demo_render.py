"""Render provenance-labelled tracking demos from real footage and CSV rows."""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

_BAR_HEIGHT = 72
_COLORS = ((53, 190, 255), (92, 222, 113), (255, 158, 70), (213, 106, 255), (74, 220, 224))


@dataclass(frozen=True)
class Observation:
    """One unmodified tracker observation."""

    frame: int
    track_id: str
    cls: str
    x: float
    y: float


def caption_lines(sport: str, coordinate_space: str, quality: str) -> tuple[str, str]:
    """Return explicit provenance and corpus captions for a demo."""
    space = coordinate_space.replace("_", " ")
    return (
        "%s | coordinate space: %s | %s" % (sport, space, quality),
        "CourtVision tracking teacher -- training-only corpus",
    )


def read_tracking(path: Path) -> tuple[dict[int, list[Observation]], str]:
    """Load observed tracking rows grouped by source frame."""
    rows: dict[int, list[Observation]] = defaultdict(list)
    spaces: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if raw.get("observation", "observed") != "observed":
                continue
            try:
                item = Observation(int(float(raw["frame"])), raw["track_id"], raw.get("cls", "object"),
                                   float(raw["x"]), float(raw["y"]))
            except (KeyError, ValueError):
                continue
            rows[item.frame].append(item)
            spaces.add(raw.get("coordinate_space", "unspecified"))
    if not rows:
        raise ValueError("No observed tracking rows in %s" % path)
    if len(spaces) != 1:
        raise ValueError("Tracking CSV must have one coordinate space, got %s" % sorted(spaces))
    return rows, spaces.pop()


def color_for(track_id: str) -> tuple[int, int, int]:
    """Use a stable BGR color per tracker ID."""
    return _COLORS[int(hashlib.sha1(track_id.encode()).hexdigest(), 16) % len(_COLORS)]


def draw_caption(frame: np.ndarray, lines: tuple[str, str]) -> np.ndarray:
    """Add a fixed caption bar without obscuring the rendered 720p output."""
    canvas = np.zeros((frame.shape[0] + _BAR_HEIGHT, frame.shape[1], 3), dtype=np.uint8)
    canvas[:frame.shape[0]] = frame
    for index, line in enumerate(lines):
        cv2.putText(canvas, line, (20, frame.shape[0] + 26 + index * 27), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (245, 245, 245), 1, cv2.LINE_AA)
    return canvas


def draw_court_inset(frame: np.ndarray, observations: list[Observation]) -> None:
    """Draw real court-feet rows in a labelled inset; never project them to pixels."""
    left, top, width, height = 18, 18, 250, 140
    cv2.rectangle(frame, (left, top), (left + width, top + height), (30, 30, 30), -1)
    cv2.rectangle(frame, (left, top), (left + width, top + height), (230, 230, 230), 1)
    cv2.putText(frame, "court_feet positions", (left + 6, top + 18), cv2.FONT_HERSHEY_SIMPLEX,
                0.42, (245, 245, 245), 1, cv2.LINE_AA)
    for item in observations:
        x = left + int(np.clip(item.x / 94.0, 0, 1) * width)
        y = top + 28 + int(np.clip(item.y / 50.0, 0, 1) * (height - 32))
        cv2.circle(frame, (x, y), 5, color_for(item.track_id), -1)
        cv2.putText(frame, item.track_id, (x + 6, y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                    color_for(item.track_id), 1, cv2.LINE_AA)


def render(video: Path, tracking: Path, output: Path, sport: str, quality: str,
           start_frame: int, seconds: float, output_fps: int, source_size: tuple[int, int] | None) -> None:
    """Render observed tracks only; no interpolation or fabricated boxes are introduced."""
    observations, coordinate_space = read_tracking(tracking)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError("Cannot open footage: %s" % video)
    native_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    every = max(1, round(native_fps / output_fps))
    # Repo-embedded clips stay short; local evidence renders may run to 90s.
    total = min(int(seconds * output_fps), 90 * output_fps)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(suffix=".mp4")
    os.close(descriptor)
    temp = Path(temporary_name)
    writer = cv2.VideoWriter(str(temp), cv2.VideoWriter_fourcc(*"mp4v"), output_fps, (1280, 720))
    if not writer.isOpened():
        raise OSError("Could not create temporary video")
    trails: dict[str, deque[tuple[int, int, int]]] = defaultdict(lambda: deque(maxlen=18))
    capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    try:
        for index in range(total):
            source_frame = start_frame + index * every
            capture.set(cv2.CAP_PROP_POS_FRAMES, source_frame)
            ok, image = capture.read()
            if not ok:
                break
            image = cv2.resize(image, (1280, 720 - _BAR_HEIGHT), interpolation=cv2.INTER_AREA)
            sx = image.shape[1] / (source_size[0] if source_size else width)
            sy = image.shape[0] / (source_size[1] if source_size else height)
            current = observations.get(source_frame, [])
            if coordinate_space == "court_feet":
                draw_court_inset(image, current)
            elif coordinate_space == "image_px":
                for item in current:
                    x, y = round(item.x * sx), round(item.y * sy)
                    trail = trails[item.track_id]
                    if trail and source_frame - trail[-1][0] > every * 2:
                        trail.clear()
                    trail.append((source_frame, x, y))
                    color = color_for(item.track_id)
                    for _, ax, ay in list(trail)[:-1]:
                        cv2.circle(image, (ax, ay), 2, color, -1)
                    cv2.drawMarker(image, (x, y), color, cv2.MARKER_CROSS, 16, 2)
                    cv2.putText(image, "%s %s" % (item.cls, item.track_id), (x + 7, y - 7),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.43, color, 1, cv2.LINE_AA)
            writer.write(draw_caption(image, caption_lines(sport, coordinate_space, quality)))
    finally:
        writer.release()
        capture.release()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg is required to encode H.264")
    command = [ffmpeg, "-y", "-i", str(temp), "-c:v", "libx264", "-preset", "slow", "-crf", "25",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    finally:
        temp.unlink(missing_ok=True)
    if output.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Demo exceeds 8 MB: %s" % output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--tracking", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sport", required=True)
    parser.add_argument("--quality", required=True, help="Honest quality state shown in the caption")
    parser.add_argument("--start-frame", required=True, type=int)
    parser.add_argument("--seconds", default=15.0, type=float)
    parser.add_argument("--output-fps", default=10, type=int,
                        help="Sampling rate; 10 fps preserves common stride-3 tracker rows at 30 fps")
    parser.add_argument("--source-size", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"))
    args = parser.parse_args()
    render(args.video, args.tracking, args.output, args.sport, args.quality, args.start_frame, args.seconds,
           args.output_fps, tuple(args.source_size) if args.source_size else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
