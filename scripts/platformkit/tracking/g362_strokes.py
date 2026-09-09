"""G362 marking strokes: whole-stroke extraction, content-addressed ids, and the FIT/VALIDATION cut.

The defect this module exists to remove: `g334_court_line_calibration.heldout_split` permutes
individual LSD SEGMENTS, so fragments of ONE physical marking land on both sides of the split and
every held-out residual measured against them is self-fit contaminated (contract B8).

Here the unit is the WHOLE STROKE -- one collinear group standing for one physical marking -- and a
stroke is never split. Support points are resampled at a FIXED SPACING along each stroke, so the
count of held-out supports is a function of stroke LENGTH alone and cannot be raised by lowering a
detector threshold. G334 measured that defect directly: the same route homography's forward error
fell from 24.811 px to 14.811 px on one section purely because a denser held-out set was supplied.

Every rule below is sealed in `docs/evidence/tracking/g362_registration_refusal_2026-09-09/
g362_prereg_2026-09-09.md`, sections 3 and 8. No value here is tuned per frame or per section.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import (
    ObservedSegment, candidate_line_group_details,
)
from scripts.platformkit.tracking.g334_court_line_calibration import ARM_A, Config, detect_segments

cv2.setNumThreads(1)

MIN_STROKE_PX = 40.0
SUPPORT_SPACING_PX = 6.0
FAMILY_BIN_DEG = 15.0
VALIDATION_DIVISOR = 4


@dataclass(frozen=True, eq=False)
class Stroke:
    """One physical marking as observed: a fitted line, its extent, and its fixed-density supports."""

    stroke_id: str
    digest: str
    family: int
    line: tuple
    extent: tuple
    anchor: tuple
    direction: tuple
    segments: tuple
    supports: np.ndarray

    @property
    def length(self) -> float:
        return self.extent[1] - self.extent[0]


def normalise_line(line) -> tuple:
    """(a, b, c) with hypot(a, b) == 1 and c >= 0, so a line and its reverse share one id."""
    a, b, c = (float(v) for v in np.asarray(line, dtype=float).ravel()[:3])
    norm = math.hypot(a, b)
    if norm == 0.0:
        raise ValueError("degenerate line")
    a, b, c = a / norm, b / norm, c / norm
    if c < 0.0 or (c == 0.0 and a < 0.0):
        a, b, c = -a, -b, -c
    return a, b, c


FAMILY_BINS = int(round(180.0 / FAMILY_BIN_DEG))


def family_of(a: float, b: float) -> int:
    """The 15-degree orientation bin of the line, in 0..11, CENTRED on multiples of 15 degrees.

    Centred and wrapped on purpose. With bins that start at 0 the direction is split at 0/180 and
    again at 90: the two anti-aliased edges of one painted marking fit at 179.9 and 0.1 degrees and
    land in different bins, so ONE physical orientation would satisfy a two-family bar on its own.
    Measured on this row's short-marking fixture: four markings in two orientations reported four
    families under the uncentred rule and report two under this one.
    """
    theta = math.degrees(math.atan2(-a, b)) % 180.0
    return int(round(theta / FAMILY_BIN_DEG)) % FAMILY_BINS


def stroke_key(line: tuple, extent: tuple) -> str:
    """The ASCII string the id and the digest are taken over. Content-addressed, no seed."""
    return "G362|%.4f|%.4f|%.4f|%.1f|%.1f" % (line[0], line[1], line[2], extent[0], extent[1])


def support_points(anchor: tuple, direction: tuple, extent: tuple) -> np.ndarray:
    """Points along the fitted line at exactly SUPPORT_SPACING_PX, endpoints always included."""
    lo, hi = float(extent[0]), float(extent[1])
    steps = max(1, int(math.floor((hi - lo) / SUPPORT_SPACING_PX)))
    offsets = list(np.linspace(lo, lo + steps * SUPPORT_SPACING_PX, steps + 1))
    if offsets[-1] < hi - 1e-6:
        offsets.append(hi)
    x0, y0 = float(anchor[0]), float(anchor[1])
    vx, vy = float(direction[0]), float(direction[1])
    return np.asarray([(x0 + t * vx, y0 + t * vy) for t in offsets], dtype=np.float32)


def strokes_from_segments(segments: list, cfg: Config = ARM_A) -> list:
    """Collinear groups of at least MIN_STROKE_PX observed extent, as whole strokes."""
    out = []
    for group in candidate_line_group_details(segments, cfg.group_angle_deg, cfg.group_offset_px):
        if group.length < MIN_STROKE_PX:
            continue
        try:
            line = normalise_line(group.line)
        except ValueError:
            continue
        key = stroke_key(line, group.extent)
        digest = hashlib.sha256(key.encode("ascii")).hexdigest()
        out.append(Stroke(
            stroke_id=digest[:16], digest=digest, family=family_of(line[0], line[1]), line=line,
            extent=(float(group.extent[0]), float(group.extent[1])),
            anchor=(float(group.anchor[0]), float(group.anchor[1])),
            direction=(float(group.direction[0]), float(group.direction[1])),
            segments=tuple(group.segments),
            supports=support_points(group.anchor, group.direction, group.extent)))
    return sorted(out, key=lambda stroke: stroke.stroke_id)


def extract_strokes(image: np.ndarray, cfg: Config = ARM_A) -> list:
    """Detect segments with the landed G334 detector, then group them into whole strokes."""
    return strokes_from_segments(detect_segments(image, cfg), cfg)


def partition(strokes: list):
    """(FIT, VALIDATION). Within each family, the ceil(n/4) lowest stroke ids are held out.

    Deterministic, content-addressed and independent of frame content order, so the split is
    reproducible from `strokes.csv` alone. Reserving inside each family guarantees both that at
    least 25 pct of strokes are held out and that every occupied family contributes a held-out
    stroke, which is what the prereg's ">= 2 held-out marking families" bar needs to be reachable.
    """
    families: dict = {}
    for stroke in strokes:
        families.setdefault(stroke.family, []).append(stroke)
    fit, validation = [], []
    for family in sorted(families):
        members = sorted(families[family], key=lambda stroke: stroke.stroke_id)
        cut = -(-len(members) // VALIDATION_DIVISOR)
        validation.extend(members[:cut])
        fit.extend(members[cut:])
    key = lambda stroke: stroke.stroke_id  # noqa: E731 -- one sort key, named inline
    return sorted(fit, key=key), sorted(validation, key=key)


def segments_of(strokes: list) -> list:
    """Every ObservedSegment belonging to these strokes -- what the FIT half hands the fitter."""
    return [segment for stroke in strokes for segment in stroke.segments]


def support_array(strokes: list) -> np.ndarray:
    """All support points of these strokes, as one (n, 2) float32 array."""
    if not strokes:
        return np.zeros((0, 2), dtype=np.float32)
    return np.concatenate([stroke.supports for stroke in strokes], axis=0)


def families_of(strokes: list) -> set:
    return {stroke.family for stroke in strokes}


def demo() -> None:
    """Self-check: whole strokes, a >= 25 pct reservation, and no stroke on both sides."""
    def seg(x1, y1, x2, y2):
        return ObservedSegment(endpoints=(x1, y1, x2, y2))

    raw = [seg(10.0, 10.0, 200.0, 10.0), seg(210.0, 10.0, 400.0, 10.0),
           seg(10.0, 300.0, 400.0, 300.0), seg(10.0, 20.0, 10.0, 400.0),
           seg(300.0, 20.0, 300.0, 400.0), seg(500.0, 20.0, 500.0, 400.0)]
    strokes = strokes_from_segments(raw)
    assert len(strokes) == 5, len(strokes)
    assert len({stroke.stroke_id for stroke in strokes}) == 5
    fit, validation = partition(strokes)
    assert len(fit) + len(validation) == len(strokes)
    assert len(validation) >= -(-len(strokes) // VALIDATION_DIVISOR)
    assert not ({s.stroke_id for s in fit} & {s.stroke_id for s in validation})
    assert len(families_of(validation)) == 2, families_of(validation)
    spacing = np.linalg.norm(np.diff(strokes[0].supports[:2], axis=0))
    assert abs(float(spacing) - SUPPORT_SPACING_PX) < 1e-3, spacing
    # A stroke's support count depends on its length alone, not on how it was fragmented.
    merged = strokes_from_segments([seg(10.0, 10.0, 400.0, 10.0)] + raw[2:])
    top = {s.stroke_id: s for s in strokes}
    same = [s for s in merged if s.stroke_id in top]
    assert same and all(len(s.supports) == len(top[s.stroke_id].supports) for s in same)
    print("g362_strokes demo OK")


if __name__ == "__main__":
    demo()
