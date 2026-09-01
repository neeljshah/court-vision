"""Measured HSV field masks and the pitcher's-mound chord for baseball frames.

The mound is the only dirt island on a broadcast pitch view with live grass on
both sides at its widest row -- the home-plate dirt merges continuously with the
base-path band and is split by whoever is standing in front of it.  That makes
the mound the one anchor that can be identified positively rather than by an
assumed image ordering, and its horizontal chord is an exactly known 18 feet.

Hue note: infield dirt on the two clips measured on 2026-09-01 sits at hue 0-5
(BGR ~ (78, 88, 139) -> HSV (5, 112, 139)), i.e. below the previous hue floor of
5, so the old mask caught only a sliver at the boundary and its centroid wandered
28-33 px between consecutive frames.  Both red wrap ranges are included.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

MOUND_DIAMETER_FEET = 18.0
# Broadcast score bug: rows at or below this fraction are graphics, not field.
SCOREBOARD_TOP_FRACTION = 0.86
_DIRT_RANGES = (((0, 40, 45), (25, 255, 255)), ((165, 40, 45), (180, 255, 255)))
_GRASS_RANGE = ((35, 40, 25), (95, 255, 255))
MIN_CHORD_FRACTION = 0.20
_GRASS_PROBE_PX = 25


def _in_range(hsv: np.ndarray, bounds) -> np.ndarray:
    low, high = bounds
    return cv2.inRange(hsv, np.array(low, np.uint8), np.array(high, np.uint8))


def dirt_mask(frame: np.ndarray) -> np.ndarray:
    """Return a cleaned infield-dirt mask covering both red hue wrap ranges."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = _in_range(hsv, _DIRT_RANGES[0]) | _in_range(hsv, _DIRT_RANGES[1])
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))


def grass_mask(frame: np.ndarray) -> np.ndarray:
    """Return a live-grass mask used to bound the mound on both sides."""
    return _in_range(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), _GRASS_RANGE)


@dataclass(frozen=True)
class MoundChord:
    """The widest grass-bounded dirt run found on one frame, in pixels."""
    row: int
    left: int
    right: int
    near_edge_occluded: bool

    @property
    def width(self) -> float:
        return float(self.right - self.left)

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def pixels_per_foot_lateral(self) -> float:
        """Lateral scale at the mound row, from the known 18-foot chord.

        This is valid across the image x axis at this row only.  It is NOT an
        isotropic scale: the depth axis of a center-field pitch view was
        measured at roughly one thirteenth of it.
        """
        return self.width / MOUND_DIAMETER_FEET


def _runs(row_mask: np.ndarray) -> "zip":
    flags = (row_mask > 0).view(np.int8)
    edges = np.flatnonzero(np.diff(np.concatenate(([0], flags, [0]))))
    return zip(edges[::2], edges[1::2])


def mound_chord(frame: np.ndarray,
                min_chord_fraction: float = MIN_CHORD_FRACTION) -> Optional[MoundChord]:
    """Return the widest dirt run below the midline that has grass on both sides.

    ``min_chord_fraction`` is a detection floor, and it also bounds the lateral
    world width a found mound can imply (a chord of f*W pixels means a frame
    covers 18/f feet).  Measurement callers should pass a floor low enough that
    a genuinely wide framing could still be observed, rather than one that
    guarantees the answer they expect.
    """
    height, width = frame.shape[:2]
    dirt = dirt_mask(frame)
    grass = grass_mask(frame)
    board = int(SCOREBOARD_TOP_FRACTION * height)
    minimum = min_chord_fraction * width
    best: Optional[MoundChord] = None
    for row in range(height // 2, board):
        for left, right in _runs(dirt[row]):
            span = float(right - left)
            if span < minimum or (best is not None and span <= best.width):
                continue
            before = grass[row, max(0, left - _GRASS_PROBE_PX):left]
            after = grass[row, right:min(width, right + _GRASS_PROBE_PX)]
            if not (before.any() and after.any()):
                continue
            occluded = bool(dirt[board - 1, (left + right) // 2] > 0)
            best = MoundChord(row, int(left), int(right), occluded)
    return best


def infield_band_present(frame: np.ndarray, above_row: int,
                         minimum_fraction: float = 0.25) -> bool:
    """Return whether a wide dirt band sits above the mound row.

    On a pitch view this is the home-plate/base-path dirt.  It is deliberately
    only a presence test: the band merges with the base paths and runs off the
    frame edges, so no usable plate anchor can be taken from it.

    Running off a frame edge is also what separates the band from the mound: the
    mound is grass-bounded on both sides by construction, so its own upper half
    can never satisfy this test.
    """
    height, width = frame.shape[:2]
    dirt = dirt_mask(frame)
    for row in range(height // 6, max(height // 6 + 1, above_row)):
        for left, right in _runs(dirt[row]):
            if right - left < minimum_fraction * width:
                continue
            if left <= 0 or right >= width:
                return True
    return False
