"""Floor-only image-motion propagation within a routed broadcast shot."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from scripts.platformkit.tracking.shot_router import RouteRecord


@dataclass(frozen=True)
class MotionRecord:
    """One consecutive-frame propagation decision.

    n_fit / n_val are the FIT-set and VALIDATION-set match counts behind
    inlier_share/hull_share (n_fit) and p90_residual_px (n_val) -- see
    estimate_floor_motion. Both are 0 when no estimate was attempted
    (chain already stopped).
    """

    frame_index: int
    shot_id: int
    state: str
    accepted: bool
    reason: str
    inliers: int
    inlier_share: float
    hull_share: float
    p90_residual_px: float
    chain_length: int
    n_fit: int
    n_val: int


def _mask(frame: np.ndarray, boxes: list[tuple[float, float, float, float]] | None) -> np.ndarray:
    height, width = frame.shape[:2]
    mask = np.full((height, width), 255, dtype=np.uint8)
    mask[: round(height * 0.15)] = 0
    mask[round(height * 0.88) :] = 0
    for x, y, box_width, box_height in boxes or []:
        pad = max(3, round(max(box_width, box_height) * 0.15))
        cv2.rectangle(mask, (max(0, round(x - pad)), max(0, round(y - pad))), (min(width, round(x + box_width + pad)), min(height, round(y + box_height + pad))), 0, -1)
    return mask


def _hull_share(points: np.ndarray, shape: tuple[int, int]) -> float:
    if len(points) < 3:
        return 0.0
    return float(cv2.contourArea(cv2.convexHull(points.astype(np.float32))) / (shape[0] * shape[1]))


def fit_and_score(
    source_all: np.ndarray, target_all: np.ndarray, shape: tuple[int, int]
) -> tuple[np.ndarray | None, tuple[str, int, float, float, float, int, int]]:
    """Split matched points, fit on FIT only, score p90 on held-out VALIDATION only (B1/B8 fix).

    Every 4th matched pair by index (0, 4, 8, ...) goes to the VALIDATION set,
    the rest to the FIT set -- deterministic, stated here as the split rule.
    The homography is fit (RANSAC, 3 px) on the FIT set only; inlier share and
    hull are measured on the FIT set's kept inliers. The p90 residual, and the
    <= 3 px acceptance gate on it, are computed on the UNTOUCHED VALIDATION
    matches projected through the fitted homography -- never on points used to
    fit it. Diagnostics report (reason, inliers, share, hull, p90, n_fit, n_val).
    """
    validation = np.arange(len(source_all)) % 4 == 0
    source, target = source_all[~validation], target_all[~validation]
    val_source, val_target = source_all[validation], target_all[validation]
    n_fit, n_val = len(source), len(val_source)
    if n_fit < 4 or n_val < 1:
        return None, ("few_matches", 0, 0.0, 0.0, float("inf"), n_fit, n_val)
    matrix, mask = cv2.findHomography(source, target, cv2.RANSAC, 3.0)
    if matrix is None or mask is None or not np.isfinite(matrix).all():
        return None, ("ransac_failed", 0, 0.0, 0.0, float("inf"), n_fit, n_val)
    kept = mask.ravel().astype(bool)
    inliers = int(kept.sum())
    share = float(kept.mean())
    hull = _hull_share(source[kept], shape)
    projected = cv2.perspectiveTransform(val_source.reshape(1, -1, 2), matrix)[0]
    p90 = float(np.percentile(np.linalg.norm(projected - val_target, axis=1), 90))
    if inliers < 30:
        return None, ("few_inliers", inliers, share, hull, p90, n_fit, n_val)
    if share < 0.6:
        return None, ("low_inlier_share", inliers, share, hull, p90, n_fit, n_val)
    if hull < 0.10:
        return None, ("small_hull", inliers, share, hull, p90, n_fit, n_val)
    if p90 > 3.0:
        return None, ("high_residual", inliers, share, hull, p90, n_fit, n_val)
    return matrix, ("accepted", inliers, share, hull, p90, n_fit, n_val)


def estimate_floor_motion(
    previous: np.ndarray, current: np.ndarray, boxes: list[tuple[float, float, float, float]] | None = None
) -> tuple[np.ndarray | None, tuple[str, int, float, float, float, int, int]]:
    """Detect and match ORB features, then delegate to fit_and_score (B1/B8 held-out split)."""
    orb = cv2.ORB_create(nfeatures=500)
    previous_keys, previous_desc = orb.detectAndCompute(cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY), _mask(previous, boxes))
    current_keys, current_desc = orb.detectAndCompute(cv2.cvtColor(current, cv2.COLOR_BGR2GRAY), _mask(current, boxes))
    if previous_desc is None or current_desc is None:
        return None, ("no_descriptors", 0, 0.0, 0.0, float("inf"), 0, 0)
    if (
        previous_desc.ndim != 2
        or current_desc.ndim != 2
        or min(previous_desc.shape[0], current_desc.shape[0]) < 2
    ):
        return None, ("too_few_descriptors", 0, 0.0, 0.0, float("inf"), 0, 0)
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(previous_desc, current_desc, k=2)
    good = [first for first, second in pairs if first.distance < 0.75 * second.distance]
    if len(good) < 4:
        return None, ("few_matches", 0, 0.0, 0.0, float("inf"), 0, 0)
    source_all = np.float32([previous_keys[item.queryIdx].pt for item in good])
    target_all = np.float32([current_keys[item.trainIdx].pt for item in good])
    return fit_and_score(source_all, target_all, previous.shape[:2])


def compose_chain(matrices: list[np.ndarray]) -> np.ndarray:
    """Compose consecutive prior-to-current image homographies in order."""
    chain = np.eye(3, dtype=np.float64)
    for matrix in matrices:
        chain = matrix @ chain
    return chain


def _chain_inside(matrix: np.ndarray, shape: tuple[int, int]) -> bool:
    height, width = shape
    corners = np.float32(((width * .1, height * .1), (width * .9, height * .1), (width * .9, height * .9), (width * .1, height * .9))).reshape(1, -1, 2)
    projected = cv2.perspectiveTransform(corners, matrix)[0]
    return bool(np.all((projected[:, 0] >= 0) & (projected[:, 0] <= width) & (projected[:, 1] >= 0) & (projected[:, 1] <= height)))


def propagate_frames(
    frames: list[np.ndarray], routes: list[RouteRecord], boxes: dict[int, list[tuple[float, float, float, float]]] | None = None,
    anchors: set[int] | None = None,
) -> list[MotionRecord]:
    """Propagate only inside shots; an empty anchor set can never emit DIRECT."""
    if len(frames) != len(routes):
        raise ValueError("frames and routes must match")
    boxes, anchors = boxes or {}, anchors or set()
    records: list[MotionRecord] = []
    chain = np.eye(3, dtype=np.float64)
    chain_length, stopped = 0, False
    for position, route in enumerate(routes):
        if position == 0 or route.shot_id != routes[position - 1].shot_id:
            chain, chain_length, stopped = np.eye(3), 0, False
            records.append(MotionRecord(route.frame_index, route.shot_id, "ANCHOR", True, "anchor", 0, 0.0, 0.0, 0.0, 0, 0, 0))
            continue
        prior = routes[position - 1]
        if stopped:
            records.append(MotionRecord(route.frame_index, route.shot_id, "UNOBSERVABLE", False, "chain_stopped", 0, 0.0, 0.0, float("inf"), chain_length, 0, 0))
            continue
        matrix, diagnostics = estimate_floor_motion(frames[position - 1], frames[position], boxes.get(route.frame_index))
        reason, inliers, share, hull, p90, n_fit, n_val = diagnostics
        if matrix is None:
            stopped = True
            records.append(MotionRecord(route.frame_index, route.shot_id, "UNOBSERVABLE", False, reason, inliers, share, hull, p90, chain_length, n_fit, n_val))
            continue
        candidate = matrix @ chain
        if not _chain_inside(candidate, frames[position].shape[:2]):
            stopped = True
            records.append(MotionRecord(route.frame_index, route.shot_id, "UNOBSERVABLE", False, "chain_leaves_image", inliers, share, hull, p90, chain_length, n_fit, n_val))
            continue
        chain, chain_length = candidate, chain_length + 1
        state = "DIRECT" if route.frame_index in anchors else "PROPAGATED"
        records.append(MotionRecord(route.frame_index, route.shot_id, state, True, reason, inliers, share, hull, p90, chain_length, n_fit, n_val))
    return records
