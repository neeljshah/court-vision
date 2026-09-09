"""G352 per-frame measurement helpers and the section-by-arm accumulator.

Every quantity is measured in the 1280-wide MEASUREMENT image of the G334 prereg section 2, or in
the court feet of its section 3. Two unit corrections against `g334_run.py` are applied here and
named in the memo rather than edited into that landed row: feet are detected in the measurement
image (G334 fed 1920-wide cropped-frame foot pixels to a matrix defined on the 1280-wide image),
and the route composition is inverted through the crop-free scale (G334's `resize` carried the
TOPCUT translation while its measurement image was built from an already-cropped frame).
"""
from __future__ import annotations

import hashlib

import numpy as np

from scripts.platformkit.tracking import g334_court_template as gt
from scripts.platformkit.tracking import g334_metrics as gm
from scripts.platformkit.tracking import g352_whole_template_objective as g352

BOOT_N = 32
BOOT_PX = 1.0
EXCLUDE_PX = 3.0
LOW_MARGIN = 0.01
N_TEMPLATE = len(gt.TEMPLATE_POINTS)


def held_digest(segments: list) -> str:
    """A stable digest of the shared held-out supports, asserted identical across the arms."""
    text = ";".join("%.3f,%.3f,%.3f,%.3f" % tuple(float(v) for v in s.endpoints)
                    for s in segments)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def frame_rng(stem: str, index: int):
    """One deterministic generator per section and frame; the bootstrap never floats."""
    key = ("%s|%d|352-boot" % (stem, index)).encode("ascii")
    return np.random.default_rng(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))


def drop_near_heldout(segments: list, held_field: np.ndarray,
                      radius: float = EXCLUDE_PX) -> list:
    """Keep the segments whose own pixels stay clear of the shared held-out markings.

    ARM_A's fit set is the exact complement of the reserved supports. ARM_B detects its own
    segment set at a different LSD threshold, so support identity does not carry across; this
    proximity rule is what keeps the SHARED held-out markings out of ARM_B's search.
    """
    height, width = held_field.shape[:2]
    keep = []
    for segment in segments:
        x1, y1, x2, y2 = segment.endpoints
        steps = max(2, int(round(float(np.hypot(x2 - x1, y2 - y1)))))
        fraction = np.linspace(0.0, 1.0, steps)
        xs = np.clip(np.round(x1 + (x2 - x1) * fraction).astype(int), 0, width - 1)
        ys = np.clip(np.round(y1 + (y2 - y1) * fraction).astype(int), 0, height - 1)
        if float(np.median(held_field[ys, xs])) > radius:
            keep.append(segment)
    return keep


def foot_metrics(court_matrix, feet: list, rng):
    """Court points, how many land on the 94 x 50, and the 32 x 1 px bootstrap spread in feet."""
    points = gm.court_points(court_matrix, list(feet))
    inside = gm.inside_count(points)
    spreads: list = []
    if court_matrix is not None and len(feet):
        base = np.asarray(list(feet), dtype=np.float32)
        centre = gt.project(court_matrix, base)
        good = np.isfinite(centre).all(axis=1)
        if good.any():
            draws = []
            for _ in range(BOOT_N):
                noisy = base + rng.normal(0.0, BOOT_PX, base.shape).astype(np.float32)
                step = np.linalg.norm(gt.project(court_matrix, noisy) - centre, axis=1)
                draws.append(np.where(np.isfinite(step), step, np.nan))
            mean = np.nanmean(np.vstack(draws), axis=0)
            spreads = [float(v) for v in mean[good] if np.isfinite(v)]
    return points, inside, spreads


def template_records(matrix, support_field):
    """`g352.template_residuals` with the clip the rest of the sealed module already applies.

    The sealed archival helper tests its bounds on the UNROUNDED projection and then indexes with
    `np.round`, so a template point landing within half a pixel of the bottom or right edge raises
    IndexError; that crashed 3 of the 60 ARM_A frames after their search had already run. Nothing
    about the sealed objective changes here -- the loss and the in-search gates are untouched, and
    `_forward_loss` and `whole_template_loss` already clip exactly this way. Values and the
    in-frame test are otherwise identical to the sealed helper's.
    """
    if matrix is None:
        return []
    points = gt.project(matrix, gt.TEMPLATE_POINTS)
    height, width = support_field.shape[:2]
    out = []
    for index, point in enumerate(points):
        x, y = float(point[0]), float(point[1])
        in_frame = bool(np.isfinite(x) and np.isfinite(y)
                        and 0.0 <= x < width and 0.0 <= y < height)
        value = g352.PENALTY_PX
        if in_frame:
            column = int(min(max(round(x), 0), width - 1))
            row = int(min(max(round(y), 0), height - 1))
            value = min(float(support_field[row, column]), g352.PENALTY_PX)
        out.append((index, value, in_frame))
    return out


def percentile(values: list, q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), q)) if values else float("nan")


class ReasonTally:
    """Count the in-search gate's verdicts by rebinding the name `fit_from_groups` looks up.

    The sealed objective module is never edited; this is `g330_attempt2.MatchRecorder`'s pattern
    applied to the gate, so hypothesis-level rejections become countable.
    """

    def __init__(self):
        self.counts: dict = {}
        self._real = g352.validity_reason

    def __enter__(self):
        counts, real = self.counts, self._real

        def wrapper(matrix, shape, n_families):
            reason, n_inside = real(matrix, shape, n_families)
            counts[reason] = counts.get(reason, 0) + 1
            return reason, n_inside

        g352.validity_reason = wrapper
        return self

    def __exit__(self, *exc):
        g352.validity_reason = self._real
        return False

    def take(self) -> dict:
        taken = dict(self.counts)
        self.counts.clear()
        return taken


class Cell:
    """One section-by-arm cell. Forward statistics pool TEMPLATE POINTS, never frame medians."""

    def __init__(self, section: str, arm: str):
        self.section, self.arm = section, arm
        self.n_frames = self.valid = 0
        self.feet_total = self.feet_eval = self.feet_in = 0
        self.in_frame_points = 0
        self.n_hypotheses = 0
        self.held_segments = 0
        self.buckets: dict = {}
        self.gate_counts: dict = {}
        self.forward_in: list = []
        self.forward_all: list = []
        self.spreads: list = []
        self.margins: list = []

    def add(self, reason: str, records, feet: int, inside: int, spreads, margin,
            n_hypotheses: int, n_held: int) -> None:
        self.n_frames += 1
        self.buckets[reason] = self.buckets.get(reason, 0) + 1
        self.feet_total += feet
        self.n_hypotheses += n_hypotheses
        self.held_segments += n_held
        if reason != "valid":
            return
        self.valid += 1
        self.feet_eval += feet
        self.feet_in += inside
        self.spreads.extend(spreads)
        if margin is not None and np.isfinite(margin):
            self.margins.append(float(margin))
        for _index, value, in_frame in records:
            self.forward_all.append(value)
            if in_frame:
                self.forward_in.append(value)
                self.in_frame_points += 1

    def summary(self) -> dict:
        return {
            "n_frames": self.n_frames, "valid_frames": self.valid,
            "feet_total": self.feet_total, "feet_evaluated": self.feet_eval,
            "feet_inside": self.feet_in, "n_heldout_segments": self.held_segments,
            "forward_in_px_median": percentile(self.forward_in, 50.0),
            "forward_in_px_p90": percentile(self.forward_in, 90.0),
            "n_forward_in_points": len(self.forward_in),
            "forward_all_px_median": percentile(self.forward_all, 50.0),
            "forward_all_px_p90": percentile(self.forward_all, 90.0),
            "n_forward_all_points": len(self.forward_all),
            "in_frame_points": self.in_frame_points,
            "in_frame_denominator": N_TEMPLATE * self.valid,
            "boot_spread_p95_ft": percentile(self.spreads, 95.0),
            "n_boot_feet": len(self.spreads),
            "margin_median": percentile(self.margins, 50.0), "n_margins": len(self.margins),
            "n_low_margin": sum(1 for m in self.margins if m < LOW_MARGIN),
            "n_hypotheses": self.n_hypotheses,
            "buckets": dict(self.buckets), "gate_counts": dict(self.gate_counts),
        }
