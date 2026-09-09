"""G362 FIT-only estimation and the ONE accept/refuse decision the held-out strokes make.

The row's whole claim is this function's four return states. G334 and G352 measured a cascade that
cannot say NO: its in-search validity gate returned `valid` on 84 of 84 scored arm cells of
press-conference, interview and title-card content. Nothing there was judged on markings the fit
did not consume, so nothing there could refuse.

Here the search is G334's own complete enumeration and G334's own validity gate, both imported
unchanged, under the two objective rules the prereg seals in section 3: the whole-template
denominator and the gate applied INSIDE the search. It sees the FIT strokes' segments and nothing
else. The VALIDATION strokes then make ONE decision on the FROZEN winner: there is no refit, no
second candidate and no re-partition. Absent supports produce NO_VALIDATION and are NEVER valid.

Bars are sealed in `g362_prereg_2026-09-09.md` sections 4 and 8 and are not read from anywhere else.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import cv2
import numpy as np

from scripts.platformkit.tracking import g362_strokes as st
from scripts.platformkit.tracking.g334_court_line_calibration import (
    ARM_A, Config, FrameFit, distance_transform, enumerate_hypotheses, family_groups, gate,
    score_image_matrix, split_families,
)
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS, lookup, project

cv2.setNumThreads(1)

STATE_NO_LINES = "NO_LINES"
STATE_NO_VALIDATION = "NO_VALIDATION"
STATE_REFUSED = "REFUSED"
STATE_VALID = "VALID"
STATES = (STATE_NO_LINES, STATE_NO_VALIDATION, STATE_REFUSED, STATE_VALID)

MIN_STROKES = 4
MIN_FAMILIES = 2
MIN_VAL_FAMILIES = 2
MIN_VAL_POINTS = 30
MAX_MEDIAN_PX = 8.0
PENALTY_PX = 64.0
BASE_HEIGHT = 720


@dataclass(frozen=True, eq=False)
class Decision:
    """One frame's state and every number the memo and the CSVs quote for it."""

    state: str
    reason: str
    image_matrix: np.ndarray | None
    court_matrix: np.ndarray | None
    forward_median: float
    inverse_median: float
    n_strokes: int
    n_fit_strokes: int
    n_val_strokes: int
    n_val_families: int
    n_val_points: int
    n_inframe: int
    n_penalty: int
    n_hypotheses: int
    score: float
    scale: float
    forward: np.ndarray
    inverse: np.ndarray

    @property
    def accepted(self) -> bool:
        return self.state == STATE_VALID


def to_base_height(image: np.ndarray):
    """Resize to BASE_HEIGHT rows so every pixel quantity below is natively at 720p."""
    height, width = image.shape[:2]
    if height == BASE_HEIGHT:
        return image, 1.0
    scale = float(BASE_HEIGHT) / float(height)
    out = cv2.resize(image, (max(1, int(round(width * scale))), BASE_HEIGHT),
                     interpolation=cv2.INTER_AREA)
    return out, scale


def _point_field(shape, points: np.ndarray) -> np.ndarray:
    """Distance in pixels from every pixel to the nearest of `points`."""
    mask = np.zeros(shape[:2], dtype=np.uint8)
    if len(points):
        xs = np.clip(np.round(points[:, 0]).astype(int), 0, shape[1] - 1)
        ys = np.clip(np.round(points[:, 1]).astype(int), 0, shape[0] - 1)
        mask[ys, xs] = 255
    return cv2.distanceTransform(255 - mask, cv2.DIST_L2, 3)


def _inside(points: np.ndarray, shape) -> np.ndarray:
    return ((points[:, 0] >= 0.0) & (points[:, 0] <= shape[1] - 1.0)
            & (points[:, 1] >= 0.0) & (points[:, 1] <= shape[0] - 1.0)
            & np.isfinite(points).all(axis=1))


def bidirectional(image_matrix: np.ndarray, supports: np.ndarray, shape):
    """Forward and inverse per-point distances against the HELD-OUT supports only.

    Forward runs over the WHOLE template: a template point projected out of frame is charged
    PENALTY_PX rather than dropped, so a fit that keeps its score by throwing most of the court out
    of the image cannot buy a small median (G334's measured defect (1)).
    """
    projected = project(image_matrix, TEMPLATE_POINTS)
    inside = _inside(projected, shape)
    forward = np.full(len(projected), PENALTY_PX, dtype=float)
    if inside.any():
        field = _point_field(shape, supports)
        xs = np.round(projected[inside, 0]).astype(int)
        ys = np.round(projected[inside, 1]).astype(int)
        forward[inside] = np.minimum(field[ys, xs], PENALTY_PX)
    inverse = np.full(len(supports), PENALTY_PX, dtype=float)
    if inside.any() and len(supports):
        back = _point_field(shape, projected[inside])
        xs = np.clip(np.round(supports[:, 0]).astype(int), 0, shape[1] - 1)
        ys = np.clip(np.round(supports[:, 1]).astype(int), 0, shape[0] - 1)
        inverse = np.minimum(back[ys, xs], PENALTY_PX)
    return forward, inverse, int(inside.sum()), int((~inside).sum())


def _empty(state: str, reason: str, n_strokes: int, n_fit: int, n_val: int, n_fam: int,
           n_points: int, scale: float, n_hyp: int = 0, score: float = -1.0) -> Decision:
    return Decision(state, reason, None, None, float("nan"), float("nan"), n_strokes, n_fit, n_val,
                    n_fam, n_points, 0, 0, n_hyp, score, scale,
                    np.zeros(0, dtype=float), np.zeros(0, dtype=float))


def decide(image: np.ndarray, cfg: Config = ARM_A) -> Decision:
    """The full cascade: extract, partition, FIT-only fit, one held-out accept/refuse decision."""
    frame, scale = to_base_height(image)
    strokes = st.extract_strokes(frame, cfg)
    if len(strokes) < MIN_STROKES or len(st.families_of(strokes)) < MIN_FAMILIES:
        return _empty(STATE_NO_LINES, "too_few_strokes", len(strokes), 0, 0, 0, 0, scale)
    fit_strokes, val_strokes = st.partition(strokes)
    supports = st.support_array(val_strokes)
    n_fam = len(st.families_of(val_strokes))
    counts = (len(strokes), len(fit_strokes), len(val_strokes), n_fam, len(supports))
    if n_fam < MIN_VAL_FAMILIES or len(supports) < MIN_VAL_POINTS:
        return _empty(STATE_NO_VALIDATION, "absent_supports", *counts, scale)
    fitted = fit_whole_template(frame, st.segments_of(fit_strokes), cfg)
    if fitted.reason != "valid" or fitted.image is None:
        return _empty(STATE_REFUSED, fitted.reason, *counts, scale, fitted.n_hypotheses,
                      fitted.score)
    forward, inverse, n_in, n_out = bidirectional(fitted.image, supports, frame.shape)
    fwd, inv = float(np.median(forward)), float(np.median(inverse))
    passed = max(fwd, inv) <= MAX_MEDIAN_PX
    return Decision(STATE_VALID if passed else STATE_REFUSED,
                    "valid" if passed else "heldout_residual", fitted.image, fitted.court, fwd, inv,
                    *counts, n_in, n_out, fitted.n_hypotheses, fitted.score, scale, forward, inverse)


def whole_template_score(image_matrix, field: np.ndarray, cfg: Config):
    """Soft chamfer over the WHOLE 398-point template, not over the surviving points.

    An out-of-frame template point contributes zero to the sum and stays in the DENOMINATOR, so a
    hypothesis that keeps a high mean by throwing most of the court out of the image is ranked
    below the truth instead of above it. This is the objective G352 preregistered; its module is
    not landed on master (it lives only in the unlanded worktree a6), so the rule is reimplemented
    here on top of the landed G334 primitives rather than imported.

    Measured on this row's own synthetic fixture, where the truth is known by construction: under
    the landed surviving-points objective the argmax scores 0.980 on 72 of 398 points while the
    truth scores 0.734 on 398 of 398, and the recovery test cannot pass. That is G334's named
    defect (1), reproduced against a known truth rather than inferred from broadcast frames.
    """
    if image_matrix is None or not np.isfinite(image_matrix).all():
        return -1.0, 0
    projected = project(image_matrix, TEMPLATE_POINTS)
    if not np.isfinite(projected).all():
        return -1.0, 0
    distances, n_scored = lookup(field, projected)
    if n_scored < cfg.min_scored:
        return -1.0, n_scored
    kept = float(np.maximum(0.0, 1.0 - distances / cfg.tau).sum())
    return kept / float(len(TEMPLATE_POINTS)), n_scored


def _search(frame: np.ndarray, segments: list, cfg: Config, whole: bool, gated: bool):
    """G334's complete structured enumeration on `segments`. No random draw exists in it.

    With `gated`, the argmax is taken over GATE-VALID hypotheses only -- the validity gate runs
    INSIDE the search, not just on the winner. Measured need, on this row's own known-truth
    fixture: applied only at the end, the whole-template argmax is a collapsed quad of 38.7 px area
    that puts all 398 template points inside a ten-pixel blob and scores 0.876, so the gate refuses
    the frame outright instead of refusing that hypothesis and letting the truth win. The gate is
    evaluated only on candidates that beat the best valid score so far, which is exact -- a
    candidate scoring at or below the incumbent cannot become the argmax -- and cheap.
    """
    family_a, family_b = split_families(segments, cfg)
    groups_a, groups_b = family_groups(family_a, cfg), family_groups(family_b, cfg)
    if len(groups_a) < 2 or len(groups_b) < 2:
        return None, 0, -1.0, 0
    field = distance_transform(frame.shape, segments)
    bound = 8.0 * max(frame.shape[:2])
    scorer = whole_template_score if whole else score_image_matrix
    best, n_total = None, 0
    for groups_w, groups_l in ((groups_a, groups_b), (groups_b, groups_a)):
        for image_quad, court_quad in enumerate_hypotheses(groups_w, groups_l, cfg, bound):
            n_total += 1
            matrix = cv2.getPerspectiveTransform(court_quad, image_quad)
            score, n_scored = scorer(matrix, field, cfg)
            if best is not None and score <= best[0]:
                continue
            if gated and gate(matrix, score, n_scored, frame.shape, cfg) != "valid":
                continue
            best = (score, n_scored, matrix)
    if best is None:
        return None, n_total, -1.0, 0
    return best[2], n_total, float(best[0]), int(best[1])


def fit_whole_template(frame: np.ndarray, segments: list, cfg: Config = ARM_A) -> FrameFit:
    """FIT-only estimation: the whole-template argmax, then G334's own validity gate, unchanged."""
    matrix, n_total, score, n_scored = _search(frame, segments, cfg, True, True)
    if matrix is None:
        reason = "too_few_groups" if n_total == 0 else "no_valid_h"
        return FrameFit(None, None, score, n_scored, n_total, reason)
    reason = gate(matrix, score, n_scored, frame.shape, cfg)
    if reason != "valid":
        return FrameFit(None, None, score, n_scored, n_total, reason)
    court = np.linalg.inv(matrix)
    return FrameFit(court / court[2, 2], matrix, score, n_scored, n_total, "valid")


def raw_argmax(image: np.ndarray, cfg: Config = ARM_A):
    """The RAW negative control: the ARCHIVED surviving-points argmax on ALL segments, no gate.

    This is the permissive behaviour G334 and G352 measured, reproduced so the memo can say whether
    a refusal comes from the held-out decision or merely from a different detector or objective. It
    is reported for contrast and is never a pass or a fail on its own.
    """
    frame, scale = to_base_height(image)
    segments = st.segments_of(st.extract_strokes(frame, cfg))
    matrix, n_total, score, _n_scored = _search(frame, segments, cfg, False, False)
    return matrix, n_total, score, scale


def foot_spread_p95_ft(court_matrix, feet, digest: str, draws: int = 32) -> float:
    """Uncertainty cell: p95 court-plane displacement in feet under a 1 px image jitter."""
    if court_matrix is None or not len(feet):
        return float("nan")
    points = np.asarray(feet, dtype=np.float32).reshape(-1, 2)
    rng = np.random.default_rng(int(hashlib.sha256(digest.encode("ascii")).hexdigest()[:8], 16))
    base = project(court_matrix, points)
    spreads = []
    for _ in range(draws):
        jitter = rng.normal(0.0, 1.0, size=points.shape).astype(np.float32)
        moved = project(court_matrix, points + jitter)
        spreads.append(np.linalg.norm(moved - base, axis=1))
    stacked = np.concatenate(spreads)
    finite = stacked[np.isfinite(stacked)]
    return float(np.percentile(finite, 95)) if len(finite) else float("nan")


def demo() -> None:
    """Self-check: the four states exist, absent supports are never valid, penalties are charged."""
    from scripts.platformkit.tracking import g362_synth as synth

    assert set(STATES) == {STATE_NO_LINES, STATE_NO_VALIDATION, STATE_REFUSED, STATE_VALID}
    blank = np.full((720, 1280, 3), 46, dtype=np.uint8)
    assert decide(blank).state == STATE_NO_LINES
    matrix = synth.known_matrix()
    far = matrix.copy()
    far[0, 2] += 100000.0
    forward, inverse, n_in, n_out = bidirectional(far, np.zeros((0, 2), np.float32), (720, 1280))
    assert n_in == 0 and n_out == len(TEMPLATE_POINTS)
    assert float(np.median(forward)) == PENALTY_PX and len(inverse) == 0
    print("g362_fit_validate demo OK")


if __name__ == "__main__":
    demo()
