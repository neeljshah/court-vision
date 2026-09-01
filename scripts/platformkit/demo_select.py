"""Choose coverage-rich demo windows without admitting close-up broadcast shots."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

import cv2
import numpy as np

from scripts.platformkit.demo_render import Observation

WIDE_FRACTION_MINIMUM = 0.70


@dataclass(frozen=True)
class WindowSelection:
    """A selected source window and the measured evidence behind that choice."""

    start_frame: int
    end_frame: int
    distinct_tracks: int
    player_rows: int
    rows_per_frame: float
    wide_frames: int
    wide_fraction: float

    @property
    def score(self) -> float:
        """Return the specified distinct-track times row-density objective."""
        return self.distinct_tracks * self.rows_per_frame


def select_wide_window(
    observations: Mapping[int, Sequence[Observation]],
    wide_by_frame: Mapping[int, bool],
    starts: Iterable[int],
    window_frames: int,
    wide_fraction_minimum: float = WIDE_FRACTION_MINIMUM,
    sample_stride: int = 1,
) -> WindowSelection:
    """Maximize player-track coverage subject to the explicit wide-view constraint."""
    if window_frames < 1:
        raise ValueError("window_frames must be positive")
    if not 0.0 <= wide_fraction_minimum <= 1.0:
        raise ValueError("wide_fraction_minimum must be in [0, 1]")
    if sample_stride < 1:
        raise ValueError("sample_stride must be positive")
    best: WindowSelection | None = None
    for start in starts:
        frames = range(start, start + window_frames)
        sampled_frames = range(start, start + window_frames, sample_stride)
        sample_count = len(sampled_frames)
        wide_frames = sum(bool(wide_by_frame.get(frame, False)) for frame in sampled_frames)
        wide_fraction = wide_frames / sample_count
        if wide_fraction < wide_fraction_minimum:
            continue
        players = [item for frame in frames for item in observations.get(frame, ()) if item.cls == "player"]
        candidate = WindowSelection(
            start_frame=start,
            end_frame=start + window_frames - 1,
            distinct_tracks=len({item.track_id for item in players}),
            player_rows=len(players),
            rows_per_frame=len(players) / window_frames,
            wide_frames=wide_frames,
            wide_fraction=wide_fraction,
        )
        if best is None or (candidate.score, candidate.wide_fraction, -candidate.start_frame) > (
            best.score, best.wide_fraction, -best.start_frame
        ):
            best = candidate
    if best is None:
        raise ValueError("No candidate window satisfies the wide-frame minimum")
    return best


def grass_pixel_share(frame: np.ndarray) -> float:
    """Return green field coverage using the soccer adapter's HSV pitch range."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array((30, 0, 20)), np.array((95, 255, 255)))
    return float(np.count_nonzero(green) / green.size)


def court_polygon_share(frame: np.ndarray, corners: np.ndarray | None) -> float:
    """Return image share enclosed by a solved court polygon, or zero when absent."""
    if corners is None or np.asarray(corners).shape != (4, 2):
        return 0.0
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.asarray(corners, dtype=np.int32), 255)
    return float(np.count_nonzero(mask) / mask.size)


def npb_person_box_wide(person_boxes: Sequence[Sequence[float]], frame_height: int) -> bool:
    """Require several small people, rejecting a close-up's dominant person box."""
    heights = [float(box[3]) - float(box[1]) for box in person_boxes if len(box) >= 4 and float(box[3]) > float(box[1])]
    return len(heights) >= 4 and float(np.median(heights)) < 0.15 * frame_height


def precompute_wide_flags(
    capture: cv2.VideoCapture,
    frame_count: int,
    is_wide: Callable[[np.ndarray], bool],
    sample_stride: int,
) -> dict[int, bool]:
    """Decode once and cache the wide-view proxy at a regular source-frame stride."""
    if frame_count < 0:
        raise ValueError("frame_count must not be negative")
    if sample_stride < 1:
        raise ValueError("sample_stride must be positive")
    flags: dict[int, bool] = {}
    for frame_index in range(frame_count):
        if frame_index % sample_stride:
            if not capture.grab():
                break
            continue
        ok, frame = capture.read()
        if not ok:
            break
        flags[frame_index] = bool(is_wide(frame))
    return flags
