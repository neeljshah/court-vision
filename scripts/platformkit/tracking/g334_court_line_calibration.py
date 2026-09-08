"""G334 automatic court-line calibration: extraction, the structured search, and the per-shot fit.

No human label is consumed anywhere in this module. The design is sealed in
`docs/evidence/tracking/g334_prereg_2026-09-08.md`; every constant below is a value from its
section 4 and none may be tuned per section. The template lives in `g334_court_template`.

The one change this row makes against G210 and G210b -- which measured 0/17 with 2,048 and then
16,384 UNIFORM draws over unstructured line groups, with G210b recording that the correct groups
were in the pool on all 17 frames and that no draw ever contained them -- is the SAMPLER. Here the
hypothesis set is enumerated COMPLETELY over a structured space: two families of image lines
standing for the court's two orthogonal directions, and a small named set of court values for each.
There is no random draw in the search. G217 measured that the solver and the court model contribute
0.000000 px, so neither is rewritten: `cv2.getPerspectiveTransform` on four line intersections is
the same arithmetic as `g196.solve_homography` and `line_calibration.solve_from_lines`.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from itertools import combinations

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import (
    ObservedSegment, candidate_line_group_details, detect_lsd_segments,
)
from scripts.platformkit.g123_low_contrast_lines import enhance_contrast
from scripts.platformkit.g132_additive_candidate_union import union_segments
from scripts.platformkit.tracking.g334_court_template import (
    FAMILY_L_VALUES, FAMILY_W_VALUES, HALF_COURT_QUAD, TEMPLATE_POINTS, distance_transform, lookup,
    project,
)

SPLIT_SEED = 334
FAMILY_SEP_DEG = 20.0
ANGLE_BIN_DEG = 5.0


@dataclass(frozen=True)
class Config:
    """One sealed parameter set. ARM_A is the first design; ARM_B is the sensitivity set."""

    name: str = "A"
    lsd_min_len: float = 28.0
    group_angle_deg: float = 5.0
    group_offset_px: float = 18.0
    family_tol_deg: float = 35.0
    top_k: int = 7
    tau: float = 6.0
    score_min: float = 0.30
    min_scored: int = 60
    px_per_ft_lo: float = 4.0
    px_per_ft_hi: float = 60.0
    quad_area_min: float = 0.02
    window: int = 5
    cut_l1: float = 0.20


ARM_A = Config()
ARM_B = Config(name="B", lsd_min_len=18.0, family_tol_deg=50.0, top_k=9)


@dataclass(frozen=True)
class FrameFit:
    """One frame's winner: `court` maps image to feet, `image` maps feet to image."""

    court: np.ndarray | None
    image: np.ndarray | None
    score: float
    n_scored: int
    n_hypotheses: int
    reason: str


def detect_segments(image: np.ndarray, cfg: Config) -> list:
    """Raw LSD unioned with LSD on the contrast-enhanced frame -- `g210._groups` composition."""
    raw = detect_lsd_segments(image, cfg.lsd_min_len)
    enhanced = detect_lsd_segments(enhance_contrast(image), cfg.lsd_min_len)
    return union_segments(raw, enhanced)


def heldout_split(segments: list, stem: str, index: int, seed: int = SPLIT_SEED):
    """The sealed split: a seeded permutation, first ceil(n/2) FIT, the rest HELD-OUT."""
    key = ("%s|%d|%d" % (stem, index, seed)).encode("ascii")
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))
    order = rng.permutation(len(segments))
    cut = (len(segments) + 1) // 2
    return [segments[i] for i in order[:cut]], [segments[i] for i in order[cut:]]


def _angle(segment: ObservedSegment) -> float:
    x1, y1, x2, y2 = segment.endpoints
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0


def _circular_gap(first: float, second: float) -> float:
    gap = abs(first - second) % 180.0
    return min(gap, 180.0 - gap)


def split_families(segments: list, cfg: Config):
    """Two length-weighted angle modes at least FAMILY_SEP_DEG apart, and their members.

    Which family stands for the court's constant-y lines and which for its constant-x lines is NOT
    asserted here: `fit_frame` tries both labellings and the score decides.
    """
    if not segments:
        return [], []
    n_bins = int(round(180.0 / ANGLE_BIN_DEG))
    weights = np.zeros(n_bins)
    angles = [_angle(segment) for segment in segments]
    for angle, segment in zip(angles, segments):
        weights[min(n_bins - 1, int(angle / ANGLE_BIN_DEG))] += segment.length
    order = np.argsort(weights)[::-1]
    first, second = int(order[0]), None
    for index in order[1:]:
        if weights[index] <= 0.0:
            break
        if _circular_gap((first + 0.5) * ANGLE_BIN_DEG,
                         (int(index) + 0.5) * ANGLE_BIN_DEG) >= FAMILY_SEP_DEG:
            second = int(index)
            break
    if second is None:
        return [], []
    mode_a, mode_b = (first + 0.5) * ANGLE_BIN_DEG, (second + 0.5) * ANGLE_BIN_DEG
    family_a, family_b = [], []
    for angle, segment in zip(angles, segments):
        gap_a, gap_b = _circular_gap(angle, mode_a), _circular_gap(angle, mode_b)
        if min(gap_a, gap_b) > cfg.family_tol_deg:
            continue
        (family_a if gap_a <= gap_b else family_b).append(segment)
    return family_a, family_b


def family_groups(segments: list, cfg: Config) -> list:
    """Collinear groups of one family, the TOP_K longest, longest first."""
    groups = candidate_line_group_details(segments, cfg.group_angle_deg, cfg.group_offset_px)
    return sorted(groups, key=lambda group: group.length, reverse=True)[:cfg.top_k]


def _intersect(first: np.ndarray, second: np.ndarray):
    point = np.cross(first, second)
    if abs(point[2]) < 1e-9:
        return None
    value = point[:2] / point[2]
    return value if np.isfinite(value).all() else None


_W_COMBOS = list(combinations(range(len(FAMILY_W_VALUES)), 2))
_L_COMBOS = list(combinations(range(len(FAMILY_L_VALUES)), 2))
_W_GAPS = np.array([abs(FAMILY_W_VALUES[b] - FAMILY_W_VALUES[a]) for a, b in _W_COMBOS])
_L_GAPS = np.array([abs(FAMILY_L_VALUES[b] - FAMILY_L_VALUES[a]) for a, b in _L_COMBOS])


def enumerate_hypotheses(groups_w: list, groups_l: list, cfg: Config, bound: float):
    """Every structured hypothesis surviving the scale pre-filter, as (image quad, court quad).

    The pre-filter is a SPEED guard, not a criterion: it is twice as wide on both sides as the
    sealed PX_PER_FT_RANGE gate, which is applied afterwards to the winner over all template points.
    """
    lo, hi = cfg.px_per_ft_lo / 2.0, cfg.px_per_ft_hi * 2.0
    for wa, wb in combinations(range(len(groups_w)), 2):
        for la, lb in combinations(range(len(groups_l)), 2):
            corners = [[_intersect(groups_w[w].line, groups_l[l].line) for l in (la, lb)]
                       for w in (wa, wb)]
            flat = [point for row in corners for point in row]
            if any(point is None for point in flat):
                continue
            if max(float(np.abs(point).max()) for point in flat) > bound:
                continue
            span_l = 0.5 * (float(np.linalg.norm(corners[0][0] - corners[0][1]))
                            + float(np.linalg.norm(corners[1][0] - corners[1][1])))
            span_w = 0.5 * (float(np.linalg.norm(corners[0][0] - corners[1][0]))
                            + float(np.linalg.norm(corners[0][1] - corners[1][1])))
            ok_l = np.flatnonzero((_L_GAPS * lo <= span_l) & (span_l <= _L_GAPS * hi))
            ok_w = np.flatnonzero((_W_GAPS * lo <= span_w) & (span_w <= _W_GAPS * hi))
            if not len(ok_l) or not len(ok_w):
                continue
            image_quad = np.asarray(flat, dtype=np.float32)
            for wi in ok_w:
                w_pair = [FAMILY_W_VALUES[i] for i in _W_COMBOS[wi]]
                for li in ok_l:
                    l_pair = [FAMILY_L_VALUES[i] for i in _L_COMBOS[li]]
                    for w_order in (w_pair, w_pair[::-1]):
                        for l_order in (l_pair, l_pair[::-1]):
                            yield image_quad, np.array(
                                [(l_order[0], w_order[0]), (l_order[1], w_order[0]),
                                 (l_order[0], w_order[1]), (l_order[1], w_order[1])],
                                dtype=np.float32)


def score_image_matrix(image_matrix, field: np.ndarray, cfg: Config):
    """Soft-chamfer score density of one candidate, and the sample points it put in the image."""
    if image_matrix is None or not np.isfinite(image_matrix).all():
        return -1.0, 0
    projected = project(image_matrix, TEMPLATE_POINTS)
    if not np.isfinite(projected).all():
        return -1.0, 0
    distances, n_scored = lookup(field, projected)
    if n_scored < cfg.min_scored:
        return -1.0, n_scored
    return float(np.maximum(0.0, 1.0 - distances / cfg.tau).mean()), n_scored


def gate(image_matrix, score: float, n_scored: int, shape, cfg: Config) -> str:
    """The sealed validity gate. Returns "valid" or the name of the clause that rejected.

    G247 measured that quad shape alone does NOT separate a correct court from a wrong one, so this
    removes degenerate fits and is never reported as a correctness test.
    """
    if image_matrix is None or not np.isfinite(image_matrix).all():
        return "no_valid_h"
    if n_scored < cfg.min_scored or score < cfg.score_min:
        return "no_valid_h"
    quad = project(image_matrix, HALF_COURT_QUAD)
    if not np.isfinite(quad).all() or np.abs(quad).max() > 1e6:
        return "no_valid_h"
    if abs(float(cv2.contourArea(quad))) < cfg.quad_area_min * shape[0] * shape[1]:
        return "no_valid_h"
    if not cv2.isContourConvex(np.round(quad).astype(np.int32)):
        return "no_valid_h"
    step = np.linalg.norm(project(image_matrix, TEMPLATE_POINTS + np.float32([1.0, 0.0]))
                          - project(image_matrix, TEMPLATE_POINTS), axis=1)
    finite = step[np.isfinite(step)]
    scale = float(np.median(finite)) if len(finite) else 0.0
    if not cfg.px_per_ft_lo <= scale <= cfg.px_per_ft_hi:
        return "implausible_scale"
    return "valid"


def fit_frame(image: np.ndarray, fit_segments: list, cfg: Config) -> FrameFit:
    """The winner over the complete structured hypothesis set, built from the FIT half alone."""
    family_a, family_b = split_families(fit_segments, cfg)
    groups_a, groups_b = family_groups(family_a, cfg), family_groups(family_b, cfg)
    if len(groups_a) < 2 or len(groups_b) < 2:
        return FrameFit(None, None, -1.0, 0, 0, "too_few_groups")
    field = distance_transform(image.shape, fit_segments)
    bound = 8.0 * max(image.shape[:2])
    best, n_total = None, 0
    for groups_w, groups_l in ((groups_a, groups_b), (groups_b, groups_a)):
        for image_quad, court_quad in enumerate_hypotheses(groups_w, groups_l, cfg, bound):
            n_total += 1
            matrix = cv2.getPerspectiveTransform(court_quad, image_quad)
            score, n_scored = score_image_matrix(matrix, field, cfg)
            if best is None or score > best[0]:
                best = (score, n_scored, matrix)
    if best is None:
        return FrameFit(None, None, -1.0, 0, n_total, "no_valid_h")
    score, n_scored, image_matrix = best
    reason = gate(image_matrix, score, n_scored, image.shape, cfg)
    if reason != "valid":
        return FrameFit(None, None, score, n_scored, n_total, reason)
    court = np.linalg.inv(image_matrix)
    return FrameFit(court / court[2, 2], image_matrix, score, n_scored, n_total, "valid")


def shot_median(matrices: list):
    """Elementwise median of the normalised feet-to-image matrices of one shot run."""
    usable = [m / m[2, 2] for m in matrices if m is not None and abs(m[2, 2]) > 1e-12]
    if not usable:
        return None
    return np.median(np.stack(usable), axis=0)
