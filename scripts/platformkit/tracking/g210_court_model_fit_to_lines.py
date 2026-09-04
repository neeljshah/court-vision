"""Fit a league-specific basketball court model to G205-stable line groups.

This is an isolated, classical measurement harness.  ``fit_image`` accepts no
labels; coordinates from G140 are loaded only after all fits are complete and
are passed unchanged to G205's scorer.
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import CandidateLineGroup, detect_lsd_segments
from scripts.platformkit.g123_low_contrast_lines import enhance_contrast
from scripts.platformkit.g132_additive_candidate_union import union_segments
from scripts.platformkit.g134_grouping_stability import stable_groups
from scripts.platformkit.tracking.g196_homography_from_labelled_corners import (
    court_points_for_sport,
    full_court_lines,
)
from scripts.platformkit.tracking.g205_zero_shot_corner_probe import score_frame


ROOT = Path("docs/evidence/tracking")
TARGETS = ROOT / "g140_corner_targets/corner_pixel_targets.csv"
OUT = ROOT / "g210_court_model_fit_to_lines_artifact"
MIN_LSD_LENGTH_PX = 28.0
GROUP_ANGLE_DEG = 5.0
GROUP_OFFSET_PX = 10.0
MAX_GROUPS = 24
MAX_HYPOTHESES = 2048
HYPOTHESIS_SEED = 210
SUPPORT_DISTANCE_PX = 10.0
SUPPORT_ANGLE_DEG = 5.0
PROJECTED_CORNER_MARGIN_MULTIPLIER = 1.0
RENDER_INDICES = (0, 4, 8, 12, 16)
TRANSVERSE_NAMES = ("near_baseline", "near_free_throw", "far_free_throw", "far_baseline")
LONGITUDINAL_NAMES = ("left_sideline", "right_sideline", "lane_left", "lane_right")


@dataclass(frozen=True)
class FrameSource:
    """Source metadata needed to fit one image, deliberately without labels."""

    audit_id: str
    sport: str
    source_path: Path
    width: int
    height: int


@dataclass(frozen=True)
class FitResult:
    """A label-free court-model fit and its global line-support measurement."""

    homography_image_to_court: list[list[float]]
    support_length_px: float
    supported_groups: int
    group_count: int
    hypotheses_tested: int


def _normalise(line: np.ndarray) -> np.ndarray:
    norm = float(np.hypot(line[0], line[1]))
    if norm < 1e-12:
        raise ValueError("degenerate line")
    return np.asarray(line, dtype=float) / norm


def _court_lines(sport: str) -> dict[str, np.ndarray]:
    lane_left, lane_right = court_points_for_sport(sport)[:2, 0]
    return {
        "near_baseline": np.array((0.0, 1.0, 0.0)),
        "near_free_throw": np.array((0.0, 1.0, -19.0)),
        "far_free_throw": np.array((0.0, 1.0, -75.0)),
        "far_baseline": np.array((0.0, 1.0, -94.0)),
        "left_sideline": np.array((1.0, 0.0, 0.0)),
        "right_sideline": np.array((1.0, 0.0, -50.0)),
        "lane_left": np.array((1.0, 0.0, -float(lane_left))),
        "lane_right": np.array((1.0, 0.0, -float(lane_right))),
    }


def _intersection(first: np.ndarray, second: np.ndarray) -> np.ndarray | None:
    point = np.cross(first, second)
    if abs(float(point[2])) < 1e-8:
        return None
    return point[:2] / point[2]


def solve_line_pairs(
    image_transverse: tuple[np.ndarray, np.ndarray],
    image_longitudinal: tuple[np.ndarray, np.ndarray],
    court_transverse: tuple[np.ndarray, np.ndarray],
    court_longitudinal: tuple[np.ndarray, np.ndarray],
) -> np.ndarray | None:
    """Solve image-to-court H from two transverse and two longitudinal lines."""
    image_points, court_points = [], []
    for image_t, court_t in zip(image_transverse, court_transverse):
        for image_l, court_l in zip(image_longitudinal, court_longitudinal):
            image_point = _intersection(image_t, image_l)
            court_point = _intersection(court_t, court_l)
            if image_point is None or court_point is None:
                return None
            image_points.append(image_point)
            court_points.append(court_point)
    homography, _ = cv2.findHomography(np.float32(image_points), np.float32(court_points), 0)
    if homography is None or not np.isfinite(homography).all() or abs(float(homography[2, 2])) < 1e-12:
        return None
    return homography / homography[2, 2]


def _groups(image: np.ndarray) -> list[CandidateLineGroup]:
    baseline = detect_lsd_segments(image, MIN_LSD_LENGTH_PX)
    enhanced = detect_lsd_segments(enhance_contrast(image), MIN_LSD_LENGTH_PX)
    return stable_groups(baseline, union_segments(baseline, enhanced))


def _valid_projection(homography: np.ndarray, sport: str, width: int, height: int) -> bool:
    inverse = np.linalg.inv(homography)
    points = cv2.perspectiveTransform(court_points_for_sport(sport).reshape(1, -1, 2), inverse)[0]
    if not np.isfinite(points).all() or cv2.contourArea(points.astype(np.float32)) < 0.0025 * width * height:
        return False
    margin_x, margin_y = width * PROJECTED_CORNER_MARGIN_MULTIPLIER, height * PROJECTED_CORNER_MARGIN_MULTIPLIER
    return bool((points[:, 0] >= -margin_x).all() and (points[:, 0] <= width + margin_x).all()
                and (points[:, 1] >= -margin_y).all() and (points[:, 1] <= height + margin_y).all())


def _support(homography: np.ndarray, groups: list[CandidateLineGroup], sport: str) -> tuple[float, int]:
    cosine = float(np.cos(np.deg2rad(SUPPORT_ANGLE_DEG)))
    projected = [_normalise(homography.T @ line) for line in _court_lines(sport).values()]
    total, count = 0.0, 0
    for group in groups:
        x0, y0 = group.anchor
        explained = any(
            abs(float(line @ (x0, y0, 1.0))) <= SUPPORT_DISTANCE_PX
            and abs(float(np.dot(group.line[:2], line[:2]))) >= cosine
            for line in projected
        )
        if explained:
            total += group.length
            count += 1
    return total, count


def fit_image(image: np.ndarray, sport: str) -> FitResult | None:
    """Fit one league-specific model using only image pixels and declared sport."""
    groups = sorted(_groups(image), key=lambda group: group.length, reverse=True)[:MAX_GROUPS]
    if len(groups) < 4:
        return None
    height, width = image.shape[:2]
    model = _court_lines(sport)
    rng = random.Random(HYPOTHESIS_SEED)
    best: tuple[float, int, np.ndarray] | None = None
    tested = 0
    for _ in range(MAX_HYPOTHESES):
        selected = rng.sample(range(len(groups)), 4)
        transverse_models = rng.sample(TRANSVERSE_NAMES, 2)
        longitudinal_models = rng.sample(LONGITUDINAL_NAMES, 2)
        homography = solve_line_pairs(
            tuple(groups[index].line for index in selected[:2]),
            tuple(groups[index].line for index in selected[2:]),
            tuple(model[name] for name in transverse_models),
            tuple(model[name] for name in longitudinal_models),
        )
        tested += 1
        if homography is None or not _valid_projection(homography, sport, width, height):
            continue
        support, supported = _support(homography, groups, sport)
        candidate = (support, supported, homography)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return None
    return FitResult(best[2].astype(float).tolist(), best[0], best[1], len(groups), tested)


def _sources() -> list[FrameSource]:
    with TARGETS.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["audit_id"], []).append(row)
    if len(rows) != 68 or len(grouped) != 17 or any(len(values) != 4 for values in grouped.values()):
        raise ValueError("G140 construct changed")
    sources = []
    for audit_id, values in sorted(grouped.items()):
        row = values[0]
        sources.append(FrameSource(audit_id, "wnba" if audit_id.startswith("wnba__") else "ncaa_basketball",
                                   (TARGETS.parent / row["source_decode"]).resolve(), int(row["image_width"]), int(row["image_height"])))
    return sources


def _read_targets() -> dict[str, list[dict[str, str]]]:
    with TARGETS.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["audit_id"], []).append(row)
    return grouped


def _render(image: np.ndarray, homography: np.ndarray, sport: str, destination: Path) -> None:
    panel, inverse = image.copy(), np.linalg.inv(homography)
    for court_line in full_court_lines(sport):
        projected = cv2.perspectiveTransform(court_line.reshape(1, -1, 2), inverse)[0]
        if np.isfinite(projected).all() and np.abs(projected).max() < 1_000_000:
            cv2.polylines(panel, [np.round(projected).astype(np.int32)], False, (0, 255, 255), 2, cv2.LINE_AA)
    if not cv2.imwrite(str(destination), panel, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(destination)


def run() -> dict[str, Any]:
    """Fit all source images, then score held-out labels through G205 unchanged."""
    OUT.mkdir(exist_ok=True)
    (OUT / "renders").mkdir(exist_ok=True)
    fits: dict[str, FitResult | None] = {}
    sources = _sources()
    for index, source in enumerate(sources):
        image = cv2.imread(str(source.source_path), cv2.IMREAD_COLOR)
        if image is None or image.shape[1::-1] != (source.width, source.height):
            raise ValueError(f"bad source decode: {source.audit_id}")
        fit = fit_image(image, source.sport)
        fits[source.audit_id] = fit
        if fit is not None and index in RENDER_INDICES:
            _render(image, np.asarray(fit.homography_image_to_court), source.sport, OUT / "renders" / f"{index:02d}_{source.audit_id}.jpg")
    (OUT / "fit_records.json").write_text(json.dumps({key: None if value is None else asdict(value) for key, value in fits.items()}, indent=2) + "\n", encoding="ascii")
    targets, target_rows, frame_rows = _read_targets(), [], []
    for source in sources:
        fit = fits[source.audit_id]
        proposals: list[tuple[float, float]] = []
        if fit is not None:
            inverse = np.linalg.inv(np.asarray(fit.homography_image_to_court))
            points = cv2.perspectiveTransform(court_points_for_sport(source.sport).reshape(1, -1, 2), inverse)[0]
            proposals = [tuple(map(float, point)) for point in points]
        scored, _, all_four = score_frame(targets[source.audit_id], proposals)
        target_rows.extend(scored)
        frame_rows.append({"audit_id": source.audit_id, "sport": source.sport, "fit": fit is not None,
                           "line_support_px": "" if fit is None else f"{fit.support_length_px:.3f}",
                           "supported_groups": "" if fit is None else fit.supported_groups,
                           "group_count": "" if fit is None else fit.group_count,
                           "all_four_within_12px": all_four})
    for path, rows in ((OUT / "target_scores.csv", target_rows), (OUT / "per_frame.csv", frame_rows)):
        with path.open("w", newline="", encoding="ascii") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    errors = [float(row["nearest_proposal_distance_px"]) for row in target_rows]
    summary = {"frames_all_four": sum(bool(row["all_four_within_12px"]) for row in frame_rows), "frames_total": len(frame_rows),
               "corner_errors_px": {"min": min(errors), "median": float(np.median(errors)), "p90": float(np.percentile(errors, 90)), "max": max(errors)},
               "fits": sum(row["fit"] for row in frame_rows), "configuration": {"max_hypotheses": MAX_HYPOTHESES, "max_groups": MAX_GROUPS, "seed": HYPOTHESIS_SEED}}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    print(f"all_four={summary['frames_all_four']}/{summary['frames_total']} fits={summary['fits']}")
    return summary


if __name__ == "__main__":
    run()
