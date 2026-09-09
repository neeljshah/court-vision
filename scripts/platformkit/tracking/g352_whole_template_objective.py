"""G352 whole-template loss and in-search validity gate for G334 candidates."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import candidate_line_group_details
from scripts.platformkit.tracking import g334_court_line_calibration as g334
from scripts.platformkit.tracking import g334_court_template as template

PENALTY_PX = 48.0
MIN_IN_FRAME = 100
MIN_FAMILIES = 2


@dataclass(frozen=True)
class WholeFit:
    """A G352 search result; image maps court feet to measurement pixels."""

    image: np.ndarray | None
    loss: float
    n_in_frame: int
    n_hypotheses: int
    reason: str
    runner_up_margin: float


def _inside(points: np.ndarray, shape) -> np.ndarray:
    height, width = shape[:2]
    return ((points[:, 0] >= 0.0) & (points[:, 0] < width)
            & (points[:, 1] >= 0.0) & (points[:, 1] < height))


def _segment_points(segments: list) -> np.ndarray:
    points = []
    for segment in segments:
        x1, y1, x2, y2 = segment.endpoints
        n = max(1, int(round(float(np.hypot(x2 - x1, y2 - y1)))))
        fraction = np.linspace(0.0, 1.0, n + 1)
        points.append(np.column_stack((x1 + (x2 - x1) * fraction,
                                      y1 + (y2 - y1) * fraction)))
    return np.vstack(points) if points else np.zeros((0, 2), dtype=float)


def _projected_template_field(matrix: np.ndarray, shape) -> np.ndarray:
    mask = np.zeros(shape[:2], dtype=np.uint8)
    for polyline in template.template_polylines():
        points = template.project(matrix, polyline)
        if np.isfinite(points).all() and np.abs(points).max() <= 1e6:
            cv2.polylines(mask, [np.round(points).astype(np.int32)], False, 255, 1)
    return cv2.distanceTransform(255 - mask, cv2.DIST_L2, 3)


def _forward_loss(matrix: np.ndarray, support_field: np.ndarray,
                  penalty_px: float) -> tuple[float, int]:
    projected = template.project(matrix, template.TEMPLATE_POINTS)
    if not np.isfinite(projected).all():
        return float("inf"), 0
    inside = _inside(projected, support_field.shape)
    forward = np.full(len(projected), penalty_px, dtype=float)
    if inside.any():
        xy = np.round(projected[inside]).astype(int)
        xy[:, 0] = np.clip(xy[:, 0], 0, support_field.shape[1] - 1)
        xy[:, 1] = np.clip(xy[:, 1], 0, support_field.shape[0] - 1)
        forward[inside] = np.minimum(support_field[xy[:, 1], xy[:, 0]], penalty_px)
    return float(forward.mean()), int(inside.sum())


def whole_template_loss(matrix: np.ndarray, support_field: np.ndarray,
                        support_segments: list, penalty_px: float = PENALTY_PX) -> tuple[float, int]:
    """Symmetric whole-template loss; off-image template points receive `penalty_px`."""
    if matrix is None or not np.isfinite(matrix).all():
        return float("inf"), 0
    forward_loss, n_inside = _forward_loss(matrix, support_field, penalty_px)
    if not np.isfinite(forward_loss):
        return float("inf"), 0
    supports = _segment_points(support_segments)
    if not len(supports):
        return float("inf"), n_inside
    reverse_field = _projected_template_field(matrix, support_field.shape)
    support_inside = _inside(supports, support_field.shape)
    reverse = np.full(len(supports), penalty_px, dtype=float)
    if support_inside.any():
        xy = np.round(supports[support_inside]).astype(int)
        xy[:, 0] = np.clip(xy[:, 0], 0, support_field.shape[1] - 1)
        xy[:, 1] = np.clip(xy[:, 1], 0, support_field.shape[0] - 1)
        reverse[support_inside] = np.minimum(reverse_field[xy[:, 1], xy[:, 0]], penalty_px)
    return float((forward_loss + reverse.mean()) / 2.0), n_inside


def _signed_area(points: np.ndarray) -> float:
    x, y = points[:, 0], points[:, 1]
    return float((x * np.roll(y, -1) - y * np.roll(x, -1)).sum() / 2.0)


def validity_reason(matrix: np.ndarray, shape, n_families: int) -> tuple[str, int]:
    """Apply G352's finite, coverage, orientation, scale, and non-fold gates."""
    if n_families < MIN_FAMILIES:
        return "too_few_groups", 0
    if matrix is None or not np.isfinite(matrix).all() or abs(matrix[2, 2]) < 1e-12:
        return "no_valid_h", 0
    try:
        np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return "no_valid_h", 0
    points = template.project(matrix, template.TEMPLATE_POINTS)
    if not np.isfinite(points).all():
        return "no_valid_h", 0
    n_inside = int(_inside(points, shape).sum())
    if n_inside < MIN_IN_FRAME:
        return "low_in_frame", n_inside
    quad = template.project(matrix, template.HALF_COURT_QUAD)
    if not np.isfinite(quad).all() or np.abs(quad).max() > 1e6:
        return "no_valid_h", n_inside
    if _signed_area(quad) <= 0.0 or not cv2.isContourConvex(np.round(quad).astype(np.int32)):
        return "folded", n_inside
    if abs(_signed_area(quad)) < 0.02 * shape[0] * shape[1]:
        return "implausible_scale", n_inside
    shifted = template.project(matrix, template.TEMPLATE_POINTS + np.float32([1.0, 0.0]))
    scale = np.linalg.norm(shifted - points, axis=1)
    scale = scale[np.isfinite(scale)]
    if not len(scale) or not 4.0 <= float(np.median(scale)) <= 60.0:
        return "implausible_scale", n_inside
    return "valid", n_inside


def _groups(segments: list, cfg: g334.Config):
    first, second = g334.split_families(segments, cfg)
    return g334.family_groups(first, cfg), g334.family_groups(second, cfg)


def fit_whole_template(image: np.ndarray, fit_segments: list,
                       cfg: g334.Config = g334.ARM_A) -> WholeFit:
    """Exhaustively rank valid G334 hypotheses by the sealed G352 loss."""
    groups_a, groups_b = _groups(fit_segments, cfg)
    if len(groups_a) < 2 or len(groups_b) < 2:
        return WholeFit(None, float("inf"), 0, 0, "too_few_groups", float("nan"))
    field = template.distance_transform(image.shape, fit_segments)
    return fit_from_groups(image.shape, groups_a, groups_b, field, fit_segments, cfg)


def fit_from_groups(shape, groups_a: list, groups_b: list, support_field: np.ndarray,
                    support_segments: list, cfg: g334.Config = g334.ARM_A) -> WholeFit:
    """Rank supplied physical-line groups, used by the synthetic known-H gate."""
    ranked, total, best_loss = [], 0, float("inf")
    for first, second in ((groups_a, groups_b), (groups_b, groups_a)):
        for image_quad, court_quad in g334.enumerate_hypotheses(first, second, cfg, 8.0 * max(shape[:2])):
            total += 1
            matrix = cv2.getPerspectiveTransform(court_quad, image_quad)
            reason, n_inside = validity_reason(matrix, shape, MIN_FAMILIES)
            if reason != "valid":
                continue
            forward_loss, _ = _forward_loss(matrix, support_field, PENALTY_PX)
            if forward_loss / 2.0 >= best_loss:
                continue
            loss, _ = whole_template_loss(matrix, support_field, support_segments)
            if np.isfinite(loss):
                ranked.append((loss, matrix, n_inside))
                best_loss = min(best_loss, loss)
    if not ranked:
        return WholeFit(None, float("inf"), 0, total, "no_valid_h", float("nan"))
    ranked.sort(key=lambda item: item[0])
    best = ranked[0]
    margin = ranked[1][0] - best[0] if len(ranked) > 1 else float("inf")
    return WholeFit(best[1], best[0], best[2], total, "valid", float(margin))


def reserve_supports(segments: list, stem: str, frame_index: int,
                     cfg: g334.Config = g334.ARM_A) -> tuple[list, list]:
    """Reserve whole collinear supports by a deterministic G352 hash order."""
    groups = candidate_line_group_details(segments, cfg.group_angle_deg, cfg.group_offset_px)
    ranked = sorted(enumerate(groups), key=lambda item: hashlib.sha256(
        ("%s|%d|%d|352" % (stem, frame_index, item[0])).encode("ascii")).digest())
    held_n = max(1, int(np.ceil(len(ranked) * 0.25))) if ranked else 0
    held_ids = {index for index, _group in ranked[:held_n]}
    fit, held = [], []
    for index, group in enumerate(groups):
        (held if index in held_ids else fit).extend(group.segments)
    return fit, held


def template_residuals(matrix: np.ndarray, support_field: np.ndarray) -> list[tuple[int, float, bool]]:
    """Return one forward residual record per template point for finisher archival."""
    points = template.project(matrix, template.TEMPLATE_POINTS)
    inside = _inside(points, support_field.shape)
    out = []
    for index, point in enumerate(points):
        value = PENALTY_PX
        if inside[index]:
            x, y = np.round(point).astype(int)
            value = min(float(support_field[y, x]), PENALTY_PX)
        out.append((index, value, bool(inside[index])))
    return out
